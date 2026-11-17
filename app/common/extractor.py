"""Extracción de campos de documentos tributarios.

- TextractExtractor: usa Amazon Textract (AnalyzeExpense), servicio AIaaS
  de AWS especializado en facturas y boletas.
- SimuladoExtractor: lee los campos desde los metadatos PNG de las imágenes
  de muestra; sirve para pruebas automáticas sin credenciales de AWS.

Ambos devuelven el mismo diccionario, así el resto del sistema no cambia.
"""
import io
import json

import numpy as np
from PIL import Image, ImageFilter

from . import config
from .validaciones import buscar_rut, limpiar_monto

CAMPOS_TEXTRACT = {
    "INVOICE_RECEIPT_ID": "folio",
    "INVOICE_RECEIPT_DATE": "fecha",
    "VENDOR_NAME": "emisor",
    "SUBTOTAL": "neto",
    "TAX": "iva",
    "TOTAL": "total",
}


def calidad_imagen(contenido: bytes) -> float:
    """Nitidez de 0 a 1 según la varianza de bordes (una foto borrosa tiene pocos bordes)."""
    try:
        img = Image.open(io.BytesIO(contenido)).convert("L")
    except Exception:
        return 0.5  # PDF u otro formato: valor neutro
    img.thumbnail((1200, 1200))
    bordes = np.asarray(img.filter(ImageFilter.FIND_EDGES), dtype=np.float32)
    return round(float(min(bordes.var() / 2500.0, 1.0)), 3)


def _resultado(campos, confianzas, texto, calidad, motor):
    return {
        "motor": motor,
        "campos": campos,
        "rut_emisor": campos.get("rut_emisor") or buscar_rut(texto),
        "confianzas": confianzas,
        "calidad_imagen": calidad,
    }


class TextractExtractor:
    def __init__(self, region=config.AWS_REGION):
        import boto3
        self.cliente = boto3.client("textract", region_name=region)

    def extraer(self, contenido: bytes) -> dict:
        r = self.cliente.analyze_expense(Document={"Bytes": contenido})
        campos, confianzas, textos = {}, {}, []
        for doc in r.get("ExpenseDocuments", []):
            for f in doc.get("SummaryFields", []):
                tipo = f.get("Type", {}).get("Text", "")
                valor = f.get("ValueDetection", {}).get("Text", "")
                etiqueta = f.get("LabelDetection", {}).get("Text", "")
                textos.append(f"{etiqueta} {valor}")
                nombre = CAMPOS_TEXTRACT.get(tipo)
                if "RUT" in etiqueta.upper() and buscar_rut(valor):
                    nombre = "rut_emisor"
                if nombre and nombre not in campos:
                    campos[nombre] = valor
                    confianzas[nombre] = f.get("ValueDetection", {}).get("Confidence", 0) / 100
            for b in doc.get("Blocks", []):
                if b.get("BlockType") == "LINE":
                    textos.append(b.get("Text", ""))
        for k in ("neto", "iva", "total"):
            if k in campos:
                campos[k] = limpiar_monto(campos[k])
        return _resultado(campos, confianzas, "\n".join(textos), calidad_imagen(contenido), "textract")


class SimuladoExtractor:
    def extraer(self, contenido: bytes) -> dict:
        calidad = calidad_imagen(contenido)
        try:
            meta = Image.open(io.BytesIO(contenido)).info.get("docuvali")
            datos = json.loads(meta) if meta else {}
        except Exception:
            datos = {}
        campos = datos.get("campos", {})
        base = 0.55 + 0.42 * calidad
        confianzas = {k: round(min(base + 0.03 * (i % 3), 0.99), 3) for i, k in enumerate(campos)}
        if datos.get("campo_dudoso") in confianzas:
            confianzas[datos["campo_dudoso"]] = 0.35
        return _resultado(campos, confianzas, json.dumps(campos), calidad, "simulado")


def crear_extractor():
    return TextractExtractor() if config.EXTRACTOR == "textract" else SimuladoExtractor()
