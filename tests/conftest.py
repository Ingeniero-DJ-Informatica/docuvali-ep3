import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
_tmp = tempfile.mkdtemp(prefix="docuvali-test-")
os.environ.update({
    "DATA_DIR": _tmp, "DB_PATH": os.path.join(_tmp, "test.db"), "UPLOAD_DIR": os.path.join(_tmp, "uploads"),
    "API_KEYS": "clave-test,clave-limite", "DOCUVALI_NO_AUTOAPP": "1",
    "EXTRACTOR": "simulado", "PREDICTOR": "local", "BROKER": "memoria",
    "MODEL_JSON": os.path.join(RAIZ, "model", "artifacts", "model.json"),
})
os.environ.setdefault("RABBITMQ_URL", "amqp://docuvali:docuvali@localhost:5672/%2F")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import crear_app  # noqa: E402
from app.common.broker import MemoriaBroker  # noqa: E402
from app.common.extractor import SimuladoExtractor  # noqa: E402
from app.common.pipeline import Procesador  # noqa: E402
from app.common.predictor import LocalPredictor  # noqa: E402
from app.common.storage import Repositorio  # noqa: E402

MUESTRAS = os.path.join(RAIZ, "data", "muestras")
CLAVE = {"X-API-Key": "clave-test"}


@pytest.fixture
def sistema(tmp_path):
    repo = Repositorio(str(tmp_path / "db.sqlite"))
    predictor = LocalPredictor()
    broker = MemoriaBroker(Procesador(repo, SimuladoExtractor(), predictor))
    app = crear_app(repo=repo, broker=broker, predictor=predictor, limite_por_min=1000)
    return TestClient(app), repo, broker


@pytest.fixture
def doc_limpio():
    return {"tipo_documento": "factura", "calidad_imagen": 0.9, "confianza_ocr_media": 0.95,
            "confianza_ocr_min": 0.88, "campos_detectados": 1.0, "rut_valido": 1, "iva_cuadra": 1,
            "total_cuadra": 1, "coincide_xml": 1, "monto_total": 119000}


@pytest.fixture
def doc_dudoso():
    return {"tipo_documento": "factura", "calidad_imagen": 0.3, "confianza_ocr_media": 0.7,
            "confianza_ocr_min": 0.25, "campos_detectados": 0.67, "rut_valido": 0, "iva_cuadra": 0,
            "total_cuadra": 1, "coincide_xml": 0, "monto_total": 540000}
