"""Elimina el endpoint de SageMaker para no consumir crédito de AWS Academy."""
import sys

import boto3

nombre = sys.argv[1] if len(sys.argv) > 1 else "docuvali-endpoint"
sm = boto3.client("sagemaker")
config = sm.describe_endpoint(EndpointName=nombre)["EndpointConfigName"]
sm.delete_endpoint(EndpointName=nombre)
sm.delete_endpoint_config(EndpointConfigName=config)
print(f"Endpoint {nombre} eliminado. Para volver a crearlo: python deploy/sagemaker_desplegar.py --sin-entrenamiento")
