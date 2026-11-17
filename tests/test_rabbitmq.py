"""Pruebas de interoperabilidad con RabbitMQ real (API -> cola -> worker -> resultado).

Se omiten si no hay un RabbitMQ disponible (variable RABBITMQ_URL).
"""
import os
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

from app.api.main import crear_app
from app.common import config
from app.common.broker import RabbitBroker
from app.common.predictor import LocalPredictor
from app.common.storage import Repositorio
from tests.conftest import CLAVE, MUESTRAS, RAIZ


def _rabbit_disponible():
    try:
        import pika
        pika.BlockingConnection(pika.URLParameters(config.RABBITMQ_URL)).close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _rabbit_disponible(), reason="RabbitMQ no disponible")


@pytest.fixture(scope="module")
def entorno():
    broker = RabbitBroker()
    broker.estado()
    broker.canal.queue_purge(config.COLA_TRABAJOS)
    broker.canal.queue_purge(config.COLA_FALLIDOS)
    worker = subprocess.Popen([sys.executable, "-m", "app.worker.worker"], cwd=RAIZ, env=os.environ.copy(),
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    time.sleep(2)
    cliente = TestClient(crear_app(repo=Repositorio(), broker=broker, predictor=LocalPredictor(), limite_por_min=1000))
    yield cliente, broker
    worker.terminate()
    salida = worker.communicate(timeout=10)[0].decode()
    with open(os.path.join(RAIZ, "docs", "evidencias", "log_worker_rabbitmq.txt"), "w") as f:
        f.write(salida)


def _esperar(c, doc_id, segundos=15):
    for _ in range(segundos * 10):
        d = c.get(f"/api/v1/documentos/{doc_id}", headers=CLAVE).json()
        if d["estado"] in ("listo", "error"):
            return d
        time.sleep(0.1)
    return d


def test_cp21_interoperabilidad_api_rabbitmq_worker(entorno):
    """CP-21: la API publica en RabbitMQ y un worker independiente procesa el documento."""
    c, _ = entorno
    files = {"archivo": ("factura_correcta.png", open(f"{MUESTRAS}/factura_correcta.png", "rb"), "image/png"),
             "xml_dte": ("factura_correcta.xml", open(f"{MUESTRAS}/factura_correcta.xml", "rb"), "application/xml")}
    r = c.post("/api/v1/documentos", files=files, data={"tipo_documento": "factura"}, headers=CLAVE)
    assert r.status_code == 202
    d = _esperar(c, r.json()["id"])
    assert d["estado"] == "listo" and d["resultado"]["prediccion"]["decision"] == "APROBADO_AUTOMATICO"


def test_cp22_mensaje_fallido_va_a_dlq(entorno):
    """CP-22: un mensaje que falla 3 veces termina en la cola de fallidos (DLQ)."""
    c, broker = entorno
    antes = broker.estado()["fallidos"]
    Repositorio().crear("sinarchivo01", "factura", "x.png", "test")
    broker.publicar_trabajo({"id": "sinarchivo01", "tipo_documento": "factura"})  # no existe la imagen
    for _ in range(100):
        if broker.estado()["fallidos"] > antes:
            break
        time.sleep(0.1)
    assert broker.estado()["fallidos"] == antes + 1
    assert c.get("/api/v1/documentos/sinarchivo01", headers=CLAVE).json()["estado"] == "error"
