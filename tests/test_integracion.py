"""Pruebas de integración de la API (flujo completo con broker en memoria)."""
import os

from fastapi.testclient import TestClient

from app.api.main import crear_app
from app.common.broker import MemoriaBroker
from app.common.pipeline import Procesador
from app.common.predictor import LocalPredictor
from app.common.storage import Repositorio
from tests.conftest import CLAVE, MUESTRAS


def _subir(cliente, nombre, tipo, con_xml=True):
    files = {"archivo": (f"{nombre}.png", open(os.path.join(MUESTRAS, f"{nombre}.png"), "rb"), "image/png")}
    xml = os.path.join(MUESTRAS, f"{nombre}.xml")
    if con_xml and os.path.exists(xml):
        files["xml_dte"] = (f"{nombre}.xml", open(xml, "rb"), "application/xml")
    return cliente.post("/api/v1/documentos", files=files, data={"tipo_documento": tipo}, headers=CLAVE)


def test_cp09_health(sistema):
    """CP-09: /health responde 200 sin autenticación (lo usa el balanceador)."""
    c, _, _ = sistema
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["estado"] == "ok"


def test_cp10_rechaza_sin_clave(sistema, doc_limpio):
    """CP-10: sin X-API-Key o con clave falsa responde 401."""
    c, _, _ = sistema
    assert c.post("/api/v1/predicciones", json=doc_limpio).status_code == 401
    assert c.post("/api/v1/predicciones", json=doc_limpio, headers={"X-API-Key": "falsa"}).status_code == 401


def test_cp11_rate_limiting(tmp_path, doc_limpio):
    """CP-11: superar el límite por minuto responde 429 con Retry-After."""
    repo = Repositorio(str(tmp_path / "rl.db"))
    c = TestClient(crear_app(repo=repo, broker=MemoriaBroker(), predictor=LocalPredictor(), limite_por_min=5))
    codigos = [c.post("/api/v1/predicciones", json=doc_limpio, headers={"X-API-Key": "clave-limite"}).status_code
               for _ in range(7)]
    assert codigos[:5] == [200] * 5 and codigos[5:] == [429, 429]


def test_cp12_validacion_de_entrada(sistema, doc_limpio):
    """CP-12: valores fuera de rango responden 422 (validación Pydantic)."""
    c, _, _ = sistema
    malo = {**doc_limpio, "calidad_imagen": 1.5, "tipo_documento": "pagare"}
    assert c.post("/api/v1/predicciones", json=malo, headers=CLAVE).status_code == 422


def test_cp13_prediccion_tiempo_real(sistema, doc_dudoso):
    """CP-13: /predicciones devuelve decisión, probabilidad y razones."""
    c, _, _ = sistema
    r = c.post("/api/v1/predicciones", json=doc_dudoso, headers=CLAVE)
    j = r.json()
    assert r.status_code == 200 and j["decision"] == "REVISION_HUMANA" and j["razones"] and "ms_modelo" in j


def test_cp14_flujo_completo_factura_correcta(sistema):
    """CP-14: imagen + XML -> cola -> OCR -> modelo -> 'Aprobado automático'."""
    c, _, broker = sistema
    r = _subir(c, "factura_correcta", "factura")
    assert r.status_code == 202 and broker.publicados[-1]["id"] == r.json()["id"]
    doc = c.get(r.json()["consultar_en"], headers=CLAVE).json()
    assert doc["estado"] == "listo"
    assert doc["resultado"]["variables"]["coincide_xml"] == 1
    assert doc["resultado"]["prediccion"]["decision"] == "APROBADO_AUTOMATICO"


def test_cp15_flujo_iva_incorrecto_va_a_revision(sistema):
    """CP-15: factura con IVA mal calculado y RUT inválido va a revisión humana."""
    c, _, _ = sistema
    doc = c.get(_subir(c, "factura_iva_incorrecto", "factura").json()["consultar_en"], headers=CLAVE).json()
    v = doc["resultado"]["variables"]
    assert v["iva_cuadra"] == 0 and v["rut_valido"] == 0
    assert doc["resultado"]["prediccion"]["decision"] == "REVISION_HUMANA"


def test_cp16_flujo_boleta_borrosa(sistema):
    """CP-16: boleta borrosa (calidad baja) va a revisión humana."""
    c, _, _ = sistema
    doc = c.get(_subir(c, "boleta_borrosa", "boleta").json()["consultar_en"], headers=CLAVE).json()
    assert doc["resultado"]["variables"]["calidad_imagen"] < 0.3
    assert doc["resultado"]["prediccion"]["decision"] == "REVISION_HUMANA"


def test_cp17_formato_no_soportado(sistema):
    """CP-17: un archivo .txt responde 415."""
    c, _, _ = sistema
    r = c.post("/api/v1/documentos", files={"archivo": ("a.txt", b"hola", "text/plain")},
               data={"tipo_documento": "factura"}, headers=CLAVE)
    assert r.status_code == 415


def test_cp18_documento_inexistente(sistema):
    """CP-18: consultar un ID que no existe responde 404."""
    c, _, _ = sistema
    assert c.get("/api/v1/documentos/noexiste", headers=CLAVE).status_code == 404


def test_cp19_metricas_dashboard(sistema, doc_limpio):
    """CP-19: /metricas resume la operación para el dashboard."""
    c, _, _ = sistema
    c.post("/api/v1/documentos/estructurado", json=doc_limpio, headers=CLAVE)
    j = c.get("/api/v1/metricas", headers=CLAVE).json()
    assert j["operacion"]["procesados"] == 1 and j["operacion"]["pct_automatico"] == 1.0
    assert j["modelo"]["regresion_logistica"]["f1"] > 0.6


def test_cp20_falla_del_modelo_no_pierde_el_documento(tmp_path, doc_limpio):
    """CP-20: si el modelo falla, el documento queda en estado 'error' (no se pierde)."""
    class ModeloCaido:
        nombre = "caido"

        def predecir(self, v):
            raise ConnectionError("endpoint no disponible")

    repo = Repositorio(str(tmp_path / "f.db"))
    proc = Procesador(repo, None, ModeloCaido())
    c = TestClient(crear_app(repo=repo, broker=MemoriaBroker(lambda m: _seguro(proc, m)),
                             predictor=ModeloCaido(), limite_por_min=100))
    r = c.post("/api/v1/documentos/estructurado", json=doc_limpio, headers=CLAVE)
    doc = c.get(r.json()["consultar_en"], headers=CLAVE).json()
    assert doc["estado"] == "error" and "endpoint no disponible" in doc["error"]
    assert c.post("/api/v1/predicciones", json=doc_limpio, headers=CLAVE).status_code == 503


def _seguro(proc, m):
    try:
        proc(m)
    except Exception:
        pass
