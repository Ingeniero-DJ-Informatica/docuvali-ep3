"""Pruebas unitarias: reglas tributarias, variables y modelo."""
import json

import joblib
import numpy as np
import pandas as pd

from app.common.features import construir, total_desde_xml
from app.common.validaciones import digito_verificador, iva_cuadra, limpiar_monto, rut_valido, total_cuadra
from model import inference
from tests.conftest import RAIZ


def test_cp01_rut_modulo11():
    """CP-01: valida RUT con el algoritmo módulo 11 del SII."""
    assert digito_verificador(76123456) in "0123456789K"
    bueno = f"76.123.456-{digito_verificador(76123456)}"
    assert rut_valido(bueno)
    assert not rut_valido("76.123.456-" + ("1" if bueno[-1] != "1" else "2"))
    assert not rut_valido("texto sin rut")


def test_cp02_monto_formato_chileno():
    """CP-02: convierte montos con punto de miles."""
    assert limpiar_monto("$ 1.234.567") == 1234567
    assert limpiar_monto("119000") == 119000
    assert limpiar_monto(None) is None


def test_cp03_iva_y_total():
    """CP-03: IVA = 19% del neto y total = neto + IVA."""
    assert iva_cuadra(100000, 19000) and not iva_cuadra(250000, 45000)
    assert total_cuadra(100000, 19000, 119000) and not total_cuadra(100000, 19000, 120000)
    assert total_cuadra(None, None, 15990)  # boleta


def test_cp04_variables_desde_ocr():
    """CP-04: arma las 10 variables del modelo a partir de la extracción."""
    ext = {"campos": {"folio": "1", "fecha": "2026-11-12", "neto": 100000.0, "iva": 19000.0, "total": 119000.0},
           "rut_emisor": f"76.123.456-{digito_verificador(76123456)}",
           "confianzas": {"neto": 0.9, "iva": 0.8, "total": 0.95}, "calidad_imagen": 0.8}
    v = construir(ext, "factura", "<MntTotal>119000</MntTotal>")
    assert v["rut_valido"] == v["iva_cuadra"] == v["total_cuadra"] == v["coincide_xml"] == 1
    assert v["confianza_ocr_min"] == 0.8 and v["campos_detectados"] == 1.0
    assert total_desde_xml("<x>sin total</x>") is None


def test_cp05_modelo_aprueba_documento_limpio(doc_limpio):
    """CP-05: un documento correcto se aprueba automáticamente."""
    m = inference.cargar_modelo(f"{RAIZ}/model/artifacts/model.json")
    p = inference.predecir(m, doc_limpio)
    assert p["decision"] == "APROBADO_AUTOMATICO" and p["probabilidad_error"] < 0.2


def test_cp06_modelo_explica_revision(doc_dudoso):
    """CP-06: un documento dudoso va a revisión y el modelo explica por qué."""
    m = inference.cargar_modelo(f"{RAIZ}/model/artifacts/model.json")
    p = inference.predecir(m, doc_dudoso)
    assert p["decision"] == "REVISION_HUMANA" and p["probabilidad_error"] > 0.9
    assert len(p["razones"]) == 3 and all(r["efecto"] == "aumenta el riesgo" for r in p["razones"])


def test_cp07_contrato_endpoint_sagemaker(doc_limpio, doc_dudoso):
    """CP-07: el handler de SageMaker acepta {'instances': [...]} y responde JSON."""
    modelo = inference.model_fn(f"{RAIZ}/model/artifacts")
    entrada = inference.input_fn(json.dumps({"instances": [doc_limpio, doc_dudoso]}), "application/json")
    cuerpo, tipo = inference.output_fn(inference.predict_fn(entrada, modelo), "application/json")
    preds = json.loads(cuerpo)["predictions"]
    assert tipo == "application/json" and [p["decision"] for p in preds] == ["APROBADO_AUTOMATICO", "REVISION_HUMANA"]


def test_cp08_inferencia_json_igual_a_scikit_learn():
    """CP-08: el modelo exportado a JSON da la misma probabilidad que el entrenado."""
    m = inference.cargar_modelo(f"{RAIZ}/model/artifacts/model.json")
    pipe = joblib.load(f"{RAIZ}/model/artifacts/model.joblib")
    df = pd.read_csv(f"{RAIZ}/data/documentos_etiquetados.csv").sample(300, random_state=1)
    df["log_monto"] = np.log1p(df.monto_total)
    a = pipe.predict_proba(df)[:, 1]
    b = np.array([inference.predecir(m, r)["probabilidad_error"] for r in df.to_dict("records")])
    assert np.max(np.abs(a - b)) < 1e-3


def test_cp23_regla_obligatoria_rut_invalido(doc_limpio):
    """CP-23: un RUT inválido siempre va a revisión, aunque el modelo lo apruebe."""
    from app.common.pipeline import aplicar_reglas
    m = inference.cargar_modelo(f"{RAIZ}/model/artifacts/model.json")
    v = {**doc_limpio, "rut_valido": 0}
    p = aplicar_reglas(inference.predecir(m, v), v)
    assert p["decision"] == "REVISION_HUMANA" and p["regla_aplicada"]


def test_cp24_ocr_local_lee_factura():
    """CP-24: el OCR local (Tesseract) lee RUT, neto, IVA y total de una factura de muestra."""
    import shutil
    import pytest
    if not shutil.which("tesseract"):
        pytest.skip("Tesseract no instalado")
    from app.common.extractor import LocalOCRExtractor
    r = LocalOCRExtractor().extraer(open(f"{RAIZ}/data/muestras/factura_correcta.png", "rb").read())
    c = r["campos"]
    assert rut_valido(c["rut_emisor"]) and c["neto"] == 100000 and c["iva"] == 19000 and c["total"] == 119000
