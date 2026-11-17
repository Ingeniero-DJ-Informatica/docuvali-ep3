"""Inferencia del modelo DocuVali.

Este archivo sirve en dos lugares:
1. Dentro del endpoint de Amazon SageMaker (contenedor SKLearn), mediante las
   funciones model_fn / input_fn / predict_fn / output_fn.
2. Dentro de la API, en modo local, para pruebas sin AWS (misma lógica).

La predicción usa el modelo exportado a JSON (coeficientes de la regresión
logística), así no depende de la versión de scikit-learn del contenedor.
Cada respuesta incluye una explicación: qué variables empujaron la decisión.
"""
import json
import math
import os

ETIQUETAS = {
    "calidad_imagen": "calidad de la imagen",
    "confianza_ocr_media": "confianza promedio del OCR",
    "confianza_ocr_min": "campo con menor confianza del OCR",
    "campos_detectados": "porcentaje de campos encontrados",
    "rut_valido": "RUT del emisor válido",
    "iva_cuadra": "IVA = 19% del neto",
    "total_cuadra": "total = neto + IVA",
    "coincide_xml": "coincide con el XML del SII",
    "log_monto": "monto del documento",
}


def cargar_modelo(ruta: str) -> dict:
    with open(ruta) as f:
        return json.load(f)


def _vector(modelo: dict, doc: dict) -> dict:
    """Estandariza las variables y arma el vector con nombre -> valor."""
    d = dict(doc)
    if "log_monto" not in d:
        d["log_monto"] = math.log1p(max(float(d.get("monto_total", 0)), 0.0))
    v = {}
    for nombre, media, escala in zip(modelo["numericas"], modelo["media"], modelo["escala"]):
        if nombre not in d:
            raise ValueError(f"Falta la variable '{nombre}'")
        v[nombre] = (float(d[nombre]) - media) / (escala or 1.0)
    for t in modelo["tipos"]:
        v[f"tipo_documento={t}"] = 1.0 if d.get("tipo_documento") == t else 0.0
    return v


def predecir(modelo: dict, doc: dict, top: int = 3) -> dict:
    """Devuelve probabilidad de error, decisión y las razones principales."""
    v = _vector(modelo, doc)
    aportes = {k: modelo["coeficientes"][k] * x for k, x in v.items()}
    z = modelo["intercepto"] + sum(aportes.values())
    prob = 1 / (1 + math.exp(-z))
    revision = prob >= modelo["umbral"]

    numericos = {k: a for k, a in aportes.items() if k in ETIQUETAS}
    orden = sorted(numericos.items(), key=lambda kv: kv[1], reverse=revision)
    razones = []
    for k, a in orden[:top]:
        if (a > 0) == revision:
            efecto = "aumenta el riesgo" if a > 0 else "reduce el riesgo"
            razones.append({"variable": k, "descripcion": ETIQUETAS[k],
                            "valor": doc.get(k, doc.get("monto_total")),
                            "aporte": round(a, 3), "efecto": efecto})
    return {
        "probabilidad_error": round(prob, 4),
        "decision": "REVISION_HUMANA" if revision else "APROBADO_AUTOMATICO",
        "confianza_decision": round(prob if revision else 1 - prob, 4),
        "umbral": modelo["umbral"],
        "razones": razones,
        "version_modelo": modelo["version"],
    }


# ---------- Funciones que llama el contenedor de SageMaker ----------

def model_fn(model_dir):
    return cargar_modelo(os.path.join(model_dir, "model.json"))


def input_fn(body, content_type="application/json"):
    if content_type != "application/json":
        raise ValueError(f"Tipo de contenido no soportado: {content_type}")
    datos = json.loads(body)
    if isinstance(datos, dict) and "instances" in datos:
        return datos["instances"]
    return datos if isinstance(datos, list) else [datos]


def predict_fn(instancias, modelo):
    return [predecir(modelo, doc) for doc in instancias]


def output_fn(predicciones, accept="application/json"):
    return json.dumps({"predictions": predicciones}, ensure_ascii=False), "application/json"
