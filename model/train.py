"""Entrenamiento del modelo de decisión de DocuVali.

Funciona igual en local y como *entry point* de un Training Job de
Amazon SageMaker (contenedor SKLearn). SageMaker entrega las rutas en las
variables SM_CHANNEL_TRAIN, SM_MODEL_DIR y SM_OUTPUT_DATA_DIR; todo lo que
este script imprime queda en CloudWatch Logs del Training Job.

Modelo: regresión logística con estandarización (scikit-learn).
Se elige por ser interpretable: cada coeficiente dice cuánto empuja una
variable hacia "revisión humana", lo que permite explicar cada decisión.
"""
import argparse
import glob
import json
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

TARGET = "requiere_revision"
NUMERICAS = ["calidad_imagen", "confianza_ocr_media", "confianza_ocr_min",
             "campos_detectados", "rut_valido", "iva_cuadra", "total_cuadra",
             "coincide_xml", "log_monto"]
CATEGORICAS = ["tipo_documento"]
TIPOS = ["boleta", "factura", "nota_credito"]


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["log_monto"] = np.log1p(df["monto_total"].clip(lower=0))
    return df


def metricas(y_true, y_prob, umbral):
    y_pred = (y_prob >= umbral).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "precision": round(precision_score(y_true, y_pred), 4),
        "recall": round(recall_score(y_true, y_pred), 4),
        "f1": round(f1_score(y_true, y_pred), 4),
        "roc_auc": round(roc_auc_score(y_true, y_prob), 4),
        "matriz_confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "pct_automatico": round(float((y_pred == 0).mean()), 4),
        "errores_no_detectados_pct": round(float(fn / len(y_true)), 4),
    }


def exportar_json(pipe, umbral, ruta):
    """Exporta el modelo a JSON para que la inferencia no dependa de la
    versión de scikit-learn instalada en el endpoint."""
    pre = pipe.named_steps["pre"]
    clf = pipe.named_steps["clf"]
    scaler = pre.named_transformers_["num"]
    nombres = NUMERICAS + [f"tipo_documento={t}" for t in pre.named_transformers_["cat"].categories_[0]]
    modelo = {
        "version": time.strftime("%Y%m%d-%H%M%S"),
        "umbral": umbral,
        "numericas": NUMERICAS,
        "tipos": list(pre.named_transformers_["cat"].categories_[0]),
        "media": scaler.mean_.tolist(),
        "escala": scaler.scale_.tolist(),
        "coeficientes": dict(zip(nombres, clf.coef_[0].tolist())),
        "intercepto": float(clf.intercept_[0]),
    }
    with open(ruta, "w") as f:
        json.dump(modelo, f, indent=2)
    return modelo


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--train", default=os.environ.get("SM_CHANNEL_TRAIN", "data"))
    p.add_argument("--model-dir", default=os.environ.get("SM_MODEL_DIR", "model/artifacts"))
    p.add_argument("--output-dir", default=os.environ.get("SM_OUTPUT_DATA_DIR", "model/artifacts"))
    p.add_argument("--umbral", type=float, default=0.5)  # ver análisis de umbrales en metrics.json
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    os.makedirs(a.model_dir, exist_ok=True)
    os.makedirs(a.output_dir, exist_ok=True)

    archivo = glob.glob(os.path.join(a.train, "*.csv"))[0]
    df = preparar(pd.read_csv(archivo))
    X, y = df[NUMERICAS + CATEGORICAS], df[TARGET]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, stratify=y, random_state=a.seed)
    print(f"[datos] {archivo}: {len(df)} filas | entrenamiento={len(X_tr)} prueba={len(X_te)} "
          f"| positivos={y.mean():.1%}")

    pre = ColumnTransformer([
        ("num", StandardScaler(), NUMERICAS),
        ("cat", OneHotEncoder(categories=[TIPOS], handle_unknown="ignore"), CATEGORICAS),
    ])
    pipe = Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=2000, class_weight="balanced"))])

    # Búsqueda de hiperparámetros con validación cruzada estratificada de 5 pliegues
    grid = GridSearchCV(pipe, {"clf__C": [0.01, 0.1, 1.0, 10.0]},
                        scoring="f1", cv=StratifiedKFold(5, shuffle=True, random_state=a.seed))
    t0 = time.time()
    grid.fit(X_tr, y_tr)
    print(f"[entrenamiento] mejor C={grid.best_params_['clf__C']} f1_cv={grid.best_score_:.4f} "
          f"tiempo={time.time() - t0:.1f}s")
    for c, s in zip(grid.cv_results_["param_clf__C"], grid.cv_results_["mean_test_score"]):
        print(f"[cv] C={c} f1={s:.4f}")

    mejor = grid.best_estimator_
    prob = mejor.predict_proba(X_te)[:, 1]
    m_log = metricas(y_te, prob, a.umbral)
    print("[metricas] regresion_logistica " + json.dumps(m_log))
    umbrales = {str(u): metricas(y_te, prob, u) for u in (0.35, 0.5, 0.6)}
    for u, m in umbrales.items():
        print(f"[umbral] {u}: f1={m['f1']} recall={m['recall']} automatico={m['pct_automatico']:.1%}")

    # Línea base de comparación (no se despliega: menos interpretable)
    rf = Pipeline([("pre", pre), ("clf", RandomForestClassifier(300, max_depth=8, class_weight="balanced",
                                                                 random_state=a.seed, n_jobs=-1))])
    rf.fit(X_tr, y_tr)
    m_rf = metricas(y_te, rf.predict_proba(X_te)[:, 1], a.umbral)
    print("[metricas] random_forest " + json.dumps(m_rf))

    joblib.dump(mejor, os.path.join(a.model_dir, "model.joblib"))
    modelo = exportar_json(mejor, a.umbral, os.path.join(a.model_dir, "model.json"))
    resumen = {"modelo": "LogisticRegression", "hiperparametros": {"C": grid.best_params_["clf__C"],
               "class_weight": "balanced", "umbral_decision": a.umbral},
               "regresion_logistica": m_log, "random_forest_baseline": m_rf, "analisis_umbrales": umbrales,
               "coeficientes": modelo["coeficientes"], "n_entrenamiento": len(X_tr), "n_prueba": len(X_te)}
    with open(os.path.join(a.output_dir, "metrics.json"), "w") as f:
        json.dump(resumen, f, indent=2)
    print("[ok] modelo guardado en", a.model_dir)


if __name__ == "__main__":
    main()
