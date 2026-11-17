"""Reglas de negocio tributarias chilenas usadas como variables del modelo."""
import re

PATRON_RUT = re.compile(r"\b(\d{1,2}\.?\d{3}\.?\d{3})\s*-\s*([\dkK])\b")
IVA = 0.19


def limpiar_monto(texto) -> float | None:
    """'$ 1.234.567' -> 1234567.0 (formato chileno: punto de miles)."""
    if texto is None:
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    solo = re.sub(r"[^\d,]", "", str(texto)).replace(",", ".")
    try:
        return float(solo) if solo else None
    except ValueError:
        return None


def digito_verificador(cuerpo: int) -> str:
    """Algoritmo módulo 11 del Servicio de Impuestos Internos."""
    suma, factor = 0, 2
    for d in reversed(str(cuerpo)):
        suma += int(d) * factor
        factor = 2 if factor == 7 else factor + 1
    resto = 11 - (suma % 11)
    return {11: "0", 10: "K"}.get(resto, str(resto))


def rut_valido(rut: str | None) -> bool:
    if not rut:
        return False
    m = PATRON_RUT.search(rut)
    if not m:
        return False
    cuerpo = int(m.group(1).replace(".", ""))
    return digito_verificador(cuerpo) == m.group(2).upper()


def buscar_rut(texto: str) -> str | None:
    m = PATRON_RUT.search(texto or "")
    return f"{m.group(1)}-{m.group(2).upper()}" if m else None


def iva_cuadra(neto, iva, tolerancia=2.0) -> bool:
    if neto is None or iva is None:
        return False
    return abs(iva - round(neto * IVA)) <= tolerancia


def total_cuadra(neto, iva, total, tolerancia=2.0) -> bool:
    if total is None:
        return False
    if neto is None:  # boleta: solo se informa el total
        return total > 0
    return abs(total - (neto + (iva or 0))) <= tolerancia
