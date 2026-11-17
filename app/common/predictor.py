"""Cliente del modelo: endpoint de SageMaker o modelo local (mismo código)."""
import json
import time

from model.inference import cargar_modelo, predecir

from . import config


class LocalPredictor:
    nombre = "local"

    def __init__(self, ruta=config.MODEL_JSON):
        self.modelo = cargar_modelo(ruta)

    def predecir(self, variables: dict) -> dict:
        return predecir(self.modelo, variables)


class SageMakerPredictor:
    nombre = "sagemaker"

    def __init__(self, endpoint=config.SAGEMAKER_ENDPOINT, region=config.AWS_REGION):
        import boto3
        from botocore.config import Config
        self.endpoint = endpoint
        self.cliente = boto3.client("sagemaker-runtime", region_name=region,
                                    config=Config(retries={"max_attempts": 3, "mode": "standard"},
                                                  connect_timeout=2, read_timeout=5))

    def predecir(self, variables: dict) -> dict:
        r = self.cliente.invoke_endpoint(EndpointName=self.endpoint, ContentType="application/json",
                                         Accept="application/json", Body=json.dumps(variables))
        return json.loads(r["Body"].read())["predictions"][0]


def crear_predictor():
    return SageMakerPredictor() if config.PREDICTOR == "sagemaker" else LocalPredictor()


def medir(predictor, variables):
    t0 = time.perf_counter()
    r = predictor.predecir(variables)
    return r, round((time.perf_counter() - t0) * 1000, 1)
