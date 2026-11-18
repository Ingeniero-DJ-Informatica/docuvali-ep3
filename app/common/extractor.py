"""Extracción de campos de documentos tributarios.

- TextractExtractor: usa Amazon Textract (AnalyzeExpense), servicio AIaaS
  de AWS especializado en facturas y boletas.
- LocalOCRExtractor: OCR en el propio computador con Tesseract; lee cualquier
  imagen sin AWS (menos preciso que Textract, ideal para ensayar en local).
- SimuladoExtractor: lee los campos desde los metadatos PNG de las imágenes
  de muestra; sirve para pruebas automáticas sin credenciales de AWS.

Todos devuelven el mismo diccionario, así el resto del sistema no cambia.
"""
import io
import json
import re

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


class LocalOCRExtractor:
    """OCR en el propio computador con Tesseract (sin AWS). Lee facturas y boletas chilenas
    buscando RUT, folio, fecha, neto, IVA y total con expresiones regulares."""

    MONTO = re.compile(r"\$\s*(\d{1,3}(?:\.\d{3})+|\d+)")
    NUMERO = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d{4,})(?!\s*%)")
    FOLIO = re.compile(r"(?:N\s*[°º*o]|FOLIO|Nro\.?)\s*:?\s*(\d{1,10})", re.I)
    FECHA = re.compile(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})")

    def __init__(self, idioma="spa"):
        import pytesseract
        self.ocr, self.idioma = pytesseract, idioma

    def _lineas(self, img):
        d = self.ocr.image_to_data(img, lang=self.idioma, output_type=self.ocr.Output.DICT)
        lineas = {}
        for i, palabra in enumerate(d["text"]):
            if palabra.strip() and float(d["conf"][i]) >= 0:
                clave = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
                lineas.setdefault(clave, []).append((palabra, float(d["conf"][i])))
        return [(" ".join(p for p, _ in v), sum(c for _, c in v) / len(v) / 100) for v in lineas.values()]

    def _monto(self, texto):
        m = self.MONTO.findall(texto) or self.NUMERO.findall(texto)
        return limpiar_monto(m[-1]) if m else None

    def extraer(self, contenido: bytes) -> dict:
        calidad = calidad_imagen(contenido)
        try:
            img = Image.open(io.BytesIO(contenido)).convert("L")
        except Exception:  # PDF u otro formato: en local solo se leen imágenes
            return _resultado({}, {}, "", calidad, "tesseract")
        if max(img.size) < 1400:  # agrandar fotos pequeñas mejora el OCR
            f = 1400 / max(img.size)
            img = img.resize((int(img.width * f), int(img.height * f)))
        lineas = self._lineas(img)
        texto = "\n".join(t for t, _ in lineas)
        campos, confianzas = {}, {}

        def guardar(nombre, valor, conf):
            if valor not in (None, "") and nombre not in campos:
                campos[nombre], confianzas[nombre] = valor, round(conf, 3)

        for t, conf in lineas:
            mayus = t.upper()
            if "NETO" in mayus:
                guardar("neto", self._monto(t), conf)
            elif "IVA" in mayus and "TOTAL" not in mayus:
                guardar("iva", self._monto(t), conf)
            elif "TOTAL" in mayus and "SUB" not in mayus:
                guardar("total", self._monto(t), conf)
            if (m := self.FOLIO.search(t)):
                guardar("folio", m.group(1), conf)
            if (m := self.FECHA.search(t)):
                guardar("fecha", f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}", conf)
            if (r := buscar_rut(t)):
                guardar("rut_emisor", r, conf)
        if lineas:
            guardar("emisor", lineas[0][0], lineas[0][1])
        return _resultado(campos, confianzas, texto, calidad, "tesseract")


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
    """textract = Amazon Textract (AWS) · local = Tesseract en el computador · simulado = pruebas automáticas."""
    if config.EXTRACTOR == "textract":
        return TextractExtractor()
    if config.EXTRACTOR == "local":
        return LocalOCRExtractor()
    return SimuladoExtractor()
