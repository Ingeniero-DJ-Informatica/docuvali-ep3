"""Genera el dataset de entrenamiento de DocuVali (EP3).

Cada fila representa un documento tributario ya procesado por OCR (Amazon
Textract) y por las reglas de validación. La etiqueta `requiere_revision`
indica si la extracción tuvo un error que un revisor humano debió corregir.

El dataset es SINTÉTICO: se construye con las proporciones del caso
(8.000 documentos etiquetados = 20% de 40.000; 25% de fotos de mala calidad)
porque DocuVali no dispone de datos reales de clientes (Ley 21.719).
"""
import argparse
import numpy as np
import pandas as pd

TIPOS = {"factura": 33, "boleta": 39, "nota_credito": 61}


def generar(n: int = 8000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    tipo = rng.choice(list(TIPOS), size=n, p=[0.6, 0.3, 0.1])
    mala_foto = rng.random(n) < 0.25  # 25% de fotos de mala calidad (caso EP1)
    calidad = np.where(mala_foto, rng.uniform(0.15, 0.55, n), rng.uniform(0.6, 1.0, n))

    conf_media = np.clip(0.55 + 0.42 * calidad + rng.normal(0, 0.05, n), 0.3, 0.999)
    conf_min = np.clip(conf_media - rng.uniform(0.05, 0.45, n) * (1.3 - calidad), 0.05, 0.99)
    campos = np.clip(0.6 + 0.4 * calidad + rng.normal(0, 0.08, n), 0.3, 1.0)

    rut_valido = (rng.random(n) < 0.70 + 0.28 * calidad).astype(int)
    iva_cuadra = (rng.random(n) < 0.72 + 0.26 * conf_min).astype(int)
    iva_cuadra = np.where(tipo == "boleta", 1, iva_cuadra)  # la boleta no desglosa IVA
    total_cuadra = (rng.random(n) < 0.75 + 0.23 * conf_media).astype(int)
    coincide_xml = (rng.random(n) < 0.55 + 0.42 * campos).astype(int)
    monto_total = np.round(np.exp(rng.normal(11.5, 1.3, n)))  # CLP, mediana ≈ 100.000

    # Probabilidad "real" de error de extracción (lo que el revisor humano confirma)
    z = (
        -1.2
        - 4.0 * (calidad - 0.6)
        - 6.0 * (conf_min - 0.6)
        - 2.0 * (campos - 0.85)
        - 1.6 * rut_valido
        - 1.4 * iva_cuadra
        - 1.0 * total_cuadra
        - 2.2 * coincide_xml
        + 0.25 * (np.log(monto_total) - 11.5)
        + 0.4 * (tipo == "nota_credito")
        + 6.0
        + rng.normal(0, 0.9, n)
    )
    y = (rng.random(n) < 1 / (1 + np.exp(-z))).astype(int)

    return pd.DataFrame({
        "tipo_documento": tipo,
        "calidad_imagen": calidad.round(3),
        "confianza_ocr_media": conf_media.round(3),
        "confianza_ocr_min": conf_min.round(3),
        "campos_detectados": campos.round(3),
        "rut_valido": rut_valido,
        "iva_cuadra": iva_cuadra,
        "total_cuadra": total_cuadra,
        "coincide_xml": coincide_xml,
        "monto_total": monto_total.astype(int),
        "requiere_revision": y,
    })


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=8000)
    p.add_argument("--out", default="data/documentos_etiquetados.csv")
    a = p.parse_args()
    df = generar(a.n)
    df.to_csv(a.out, index=False)
    print(f"{len(df)} filas -> {a.out} | requiere_revision = {df.requiere_revision.mean():.1%}")
