"""Prueba de carga de DocuVali con Locust.

Local:  locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 50 -r 10 -t 60s --csv resultados
AWS:    locust -f loadtest/locustfile.py --host https://<IP-EC2> --headless -u 50 -r 10 -t 60s --csv resultados
        (definir LOCUST_API_KEY con una clave válida; con certificado autofirmado se omite la verificación TLS)
"""
import os
import random

from locust import HttpUser, between, task

CLAVE = os.environ.get("LOCUST_API_KEY", "clave-carga")
MUESTRAS = os.path.join(os.path.dirname(__file__), "..", "data", "muestras")
IMAGEN = open(os.path.join(MUESTRAS, "factura_correcta.png"), "rb").read()
XML = open(os.path.join(MUESTRAS, "factura_correcta.xml"), "rb").read()


def documento():
    malo = random.random() < 0.3
    return {"tipo_documento": random.choice(["factura", "factura", "boleta", "nota_credito"]),
            "calidad_imagen": round(random.uniform(0.15, 0.5) if malo else random.uniform(0.6, 1), 3),
            "confianza_ocr_media": round(random.uniform(0.6, 0.99), 3),
            "confianza_ocr_min": round(random.uniform(0.2, 0.6) if malo else random.uniform(0.6, 0.95), 3),
            "campos_detectados": random.choice([0.67, 0.83, 1.0]),
            "rut_valido": int(random.random() > 0.1), "iva_cuadra": int(random.random() > 0.1),
            "total_cuadra": int(random.random() > 0.05), "coincide_xml": int(random.random() > 0.1),
            "monto_total": random.randint(1000, 5_000_000)}


class ClienteContable(HttpUser):
    wait_time = between(0.5, 1.5)

    def on_start(self):
        self.client.headers["X-API-Key"] = CLAVE
        self.client.verify = False

    @task(6)
    def prediccion_tiempo_real(self):
        self.client.post("/api/v1/predicciones", json=documento(), name="POST /predicciones")

    @task(3)
    def documento_estructurado(self):
        self.client.post("/api/v1/documentos/estructurado", json=documento(), name="POST /documentos/estructurado")

    @task(1)
    def subir_imagen(self):
        self.client.post("/api/v1/documentos", name="POST /documentos (imagen)",
                         files={"archivo": ("f.png", IMAGEN, "image/png"), "xml_dte": ("f.xml", XML, "application/xml")},
                         data={"tipo_documento": "factura"})

    @task(1)
    def consultar_metricas(self):
        self.client.get("/api/v1/metricas", name="GET /metricas")
