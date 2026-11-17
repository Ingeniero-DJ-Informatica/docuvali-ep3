"""Convierte lo extraído por el OCR en las variables que usa el modelo."""
import re

from .validaciones import iva_cuadra, rut_valido, total_cuadra

CAMPOS_ESPERADOS = {
    "factura": ["rut_emisor", "folio", "fecha", "neto", "iva", "total"],
    "nota_credito": ["rut_emisor", "folio", "fecha", "neto", "iva", "total"],
    "boleta": ["rut_emisor", "folio", "fecha", "total"],
}


def total_desde_xml(xml_texto: str | None) -> float | None:
    """Lee <MntTotal> del XML del Documento Tributario Electrónico (DTE)."""
    if not xml_texto:
        return None
    m = re.search(r"<MntTotal>\s*(\d+)\s*</MntTotal>", xml_texto)
    return float(m.group(1)) if m else None


def construir(extraccion: dict, tipo_documento: str, xml_dte: str | None = None) -> dict:
    campos = dict(extraccion.get("campos", {}))
    campos["rut_emisor"] = extraccion.get("rut_emisor") or campos.get("rut_emisor")
    esperados = CAMPOS_ESPERADOS.get(tipo_documento, CAMPOS_ESPERADOS["factura"])
    encontrados = [c for c in esperados if campos.get(c) not in (None, "")]

    conf = [v for v in extraccion.get("confianzas", {}).values() if v is not None]
    neto, iva, total = campos.get("neto"), campos.get("iva"), campos.get("total")
    total_xml = total_desde_xml(xml_dte)

    return {
        "tipo_documento": tipo_documento,
        "calidad_imagen": extraccion.get("calidad_imagen", 0.5),
        "confianza_ocr_media": round(sum(conf) / len(conf), 3) if conf else 0.0,
        "confianza_ocr_min": round(min(conf), 3) if conf else 0.0,
        "campos_detectados": round(len(encontrados) / len(esperados), 3),
        "rut_valido": int(rut_valido(campos.get("rut_emisor"))),
        "iva_cuadra": 1 if tipo_documento == "boleta" else int(iva_cuadra(neto, iva)),
        "total_cuadra": int(total_cuadra(neto, iva, total)),
        "coincide_xml": int(total_xml is not None and total is not None and abs(total_xml - total) <= 2),
        "monto_total": float(total or 0),
    }
