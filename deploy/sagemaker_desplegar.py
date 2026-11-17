"""Entrena y despliega el modelo de DocuVali en Amazon SageMaker (AWS Academy).

Ejecutar desde una Notebook Instance o Studio de SageMaker, en la carpeta del repositorio:
    python deploy/sagemaker_desplegar.py
Opciones:
    --sin-entrenamiento   usa model/artifacts/model.json (si los Training Jobs están bloqueados)
    --instancia           tipo de instancia del endpoint (por defecto ml.t2.medium)
"""
import argparse
import json
import os
import tarfile
import time

import boto3
import sagemaker
from sagemaker.sklearn.estimator import SKLearn
from sagemaker.sklearn.model import SKLearnModel

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAMEWORK = "1.2-1"
PREFIJO = "docuvali-ep3"


def rol():
    try:
        return sagemaker.get_execution_role()
    except Exception:  # fuera de SageMaker: AWS Academy usa el rol LabRole
        return boto3.client("iam").get_role(RoleName="LabRole")["Role"]["Arn"]


def configurar_autoescalado(endpoint, minimo=1, maximo=2, objetivo=100):
    """Escala el endpoint entre 1 y 2 instancias según invocaciones por instancia."""
    aas = boto3.client("application-autoscaling")
    recurso = f"endpoint/{endpoint}/variant/AllTraffic"
    try:
        aas.register_scalable_target(ServiceNamespace="sagemaker", ResourceId=recurso,
                                     ScalableDimension="sagemaker:variant:DesiredInstanceCount",
                                     MinCapacity=minimo, MaxCapacity=maximo)
        aas.put_scaling_policy(
            PolicyName="docuvali-invocaciones", ServiceNamespace="sagemaker", ResourceId=recurso,
            ScalableDimension="sagemaker:variant:DesiredInstanceCount", PolicyType="TargetTrackingScaling",
            TargetTrackingScalingPolicyConfiguration={
                "TargetValue": float(objetivo),
                "PredefinedMetricSpecification": {"PredefinedMetricType": "SageMakerVariantInvocationsPerInstance"},
                "ScaleInCooldown": 300, "ScaleOutCooldown": 60})
        print(f"[autoescalado] {minimo}-{maximo} instancias, objetivo {objetivo} invocaciones/min por instancia")
    except Exception as e:
        print(f"[autoescalado] no se pudo configurar (permiso de AWS Academy?): {e}")


def probar(endpoint, n=20):
    rt = boto3.client("sagemaker-runtime")
    ejemplo = {"tipo_documento": "factura", "calidad_imagen": 0.3, "confianza_ocr_media": 0.7,
               "confianza_ocr_min": 0.25, "campos_detectados": 0.67, "rut_valido": 0, "iva_cuadra": 0,
               "total_cuadra": 1, "coincide_xml": 0, "monto_total": 540000}
    tiempos = []
    for _ in range(n):
        t0 = time.perf_counter()
        r = rt.invoke_endpoint(EndpointName=endpoint, ContentType="application/json", Body=json.dumps(ejemplo))
        cuerpo = json.loads(r["Body"].read())
        tiempos.append((time.perf_counter() - t0) * 1000)
    tiempos.sort()
    print("[prueba] respuesta:", json.dumps(cuerpo, ensure_ascii=False, indent=2))
    print(f"[prueba] {n} invocaciones | p50={tiempos[n // 2]:.0f} ms | p95={tiempos[int(n * .95) - 1]:.0f} ms")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--endpoint", default="docuvali-endpoint")
    p.add_argument("--instancia", default="ml.t2.medium")
    p.add_argument("--instancia-entrenamiento", default="ml.m5.large")
    p.add_argument("--sin-entrenamiento", action="store_true")
    a = p.parse_args()

    sesion = sagemaker.Session()
    bucket, arn = sesion.default_bucket(), rol()
    print(f"[config] región={sesion.boto_region_name} bucket={bucket} rol={arn}")

    if a.sin_entrenamiento:
        os.makedirs("/tmp/docuvali", exist_ok=True)
        with tarfile.open("/tmp/docuvali/model.tar.gz", "w:gz") as t:
            t.add(f"{RAIZ}/model/artifacts/model.json", arcname="model.json")
        model_data = sesion.upload_data("/tmp/docuvali/model.tar.gz", bucket, f"{PREFIJO}/modelo")
    else:
        datos = sesion.upload_data(f"{RAIZ}/data/documentos_etiquetados.csv", bucket, f"{PREFIJO}/datos")
        print(f"[datos] dataset subido a {datos}")
        estimador = SKLearn(entry_point="train.py", source_dir=f"{RAIZ}/model", role=arn,
                            instance_type=a.instancia_entrenamiento, instance_count=1,
                            framework_version=FRAMEWORK, py_version="py3", base_job_name="docuvali-train",
                            hyperparameters={"umbral": 0.5})
        estimador.fit({"train": datos})  # los logs del entrenamiento quedan en CloudWatch
        model_data = estimador.model_data
    print(f"[modelo] artefacto: {model_data}")

    modelo = SKLearnModel(model_data=model_data, role=arn, entry_point="inference.py",
                          source_dir=f"{RAIZ}/model", framework_version=FRAMEWORK, py_version="py3")
    modelo.deploy(initial_instance_count=1, instance_type=a.instancia, endpoint_name=a.endpoint)
    print(f"[endpoint] {a.endpoint} en servicio ({a.instancia})")
    configurar_autoescalado(a.endpoint)
    probar(a.endpoint)


if __name__ == "__main__":
    main()
