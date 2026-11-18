"""Configuración por variables de entorno (12-factor)."""
import os


def _env(nombre, defecto=None):
    return os.environ.get(nombre, defecto)


DATA_DIR = _env("DATA_DIR", "/data")
DB_PATH = _env("DB_PATH", os.path.join(DATA_DIR, "docuvali.db"))
UPLOAD_DIR = _env("UPLOAD_DIR", os.path.join(DATA_DIR, "uploads"))

API_KEYS = [k.strip() for k in _env("API_KEYS", "demo-key-cambiar").split(",") if k.strip()]
RATE_LIMIT_POR_MIN = int(_env("RATE_LIMIT_POR_MIN", "120"))
MAX_ARCHIVO_MB = float(_env("MAX_ARCHIVO_MB", "5"))

BROKER = _env("BROKER", "rabbitmq")            # rabbitmq | memoria
RABBITMQ_URL = _env("RABBITMQ_URL", "amqp://docuvali:docuvali@rabbitmq:5672/%2F")
COLA_TRABAJOS = "documentos.procesar"
COLA_FALLIDOS = "documentos.fallidos"
EXCHANGE_RESULTADOS = "docuvali.resultados"

EXTRACTOR = _env("EXTRACTOR", "textract")      # textract | local | simulado
PREDICTOR = _env("PREDICTOR", "sagemaker")     # sagemaker | local
AWS_REGION = _env("AWS_REGION", _env("AWS_DEFAULT_REGION", "us-east-1"))
SAGEMAKER_ENDPOINT = _env("SAGEMAKER_ENDPOINT", "docuvali-endpoint")
MODEL_JSON = _env("MODEL_JSON", os.path.join(os.path.dirname(__file__), "..", "..", "model", "artifacts", "model.json"))
METRICS_JSON = _env("METRICS_JSON", os.path.join(os.path.dirname(MODEL_JSON), "metrics.json"))
