"""Crea documentos de muestra (ficticios) para la demostración.

Las empresas y RUT son inventados. Cada PNG guarda sus campos en un metadato
'docuvali' que solo usa el extractor simulado (pruebas sin AWS); en AWS los
mismos archivos se leen con Amazon Textract.
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.common.validaciones import digito_verificador  # noqa: E402

SALIDA = os.path.join(os.path.dirname(__file__), "muestras")


def rut(cuerpo, valido=True):
    dv = digito_verificador(cuerpo)
    if not valido:
        dv = "0" if dv != "0" else "1"
    s = f"{cuerpo:,}".replace(",", ".")
    return f"{s}-{dv}"


def fuente(t):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, t)
        except OSError:
            continue
    return ImageFont.load_default()


def clp(n):
    return "$ " + f"{int(n):,}".replace(",", ".")


def documento(nombre, tipo, emisor, rut_emisor, folio, neto, iva, total, borroso=False, xml_total=None,
              campo_dudoso=None):
    img = Image.new("RGB", (900, 1100), "white")
    d = ImageDraw.Draw(img)
    titulo = {"factura": "FACTURA ELECTRÓNICA", "boleta": "BOLETA ELECTRÓNICA"}[tipo]
    d.rectangle([520, 40, 860, 190], outline="red", width=4)
    d.text((540, 60), f"R.U.T.: {rut_emisor}", font=fuente(24), fill="red")
    d.text((540, 100), titulo, font=fuente(22), fill="red")
    d.text((540, 140), f"N° {folio}", font=fuente(24), fill="red")
    d.text((50, 60), emisor, font=fuente(30), fill="black")
    d.text((50, 110), "Giro: Venta de insumos de oficina", font=fuente(20), fill="black")
    d.text((50, 140), "Av. Ficticia 1234, Santiago", font=fuente(20), fill="black")
    d.text((50, 240), "Fecha emisión: 12-11-2026", font=fuente(22), fill="black")
    d.text((50, 280), "Señor(es): Estudio Contable Demo Ltda.", font=fuente(22), fill="black")
    d.line([50, 340, 850, 340], fill="black", width=2)
    d.text((50, 360), "Descripción", font=fuente(22), fill="black")
    d.text((650, 360), "Valor", font=fuente(22), fill="black")
    d.text((50, 410), "Resmas papel carta (10 u.)", font=fuente(22), fill="black")
    d.text((650, 410), clp(neto or total), font=fuente(22), fill="black")
    y = 820
    if neto is not None:
        d.text((480, y), "MONTO NETO", font=fuente(24), fill="black"); d.text((680, y), clp(neto), font=fuente(24), fill="black"); y += 50
        d.text((480, y), "IVA 19%", font=fuente(24), fill="black"); d.text((680, y), clp(iva), font=fuente(24), fill="black"); y += 50
    d.text((480, y), "TOTAL", font=fuente(28), fill="black"); d.text((680, y), clp(total), font=fuente(28), fill="black")
    if borroso:
        img = img.filter(ImageFilter.GaussianBlur(4))

    campos = {"folio": str(folio), "fecha": "2026-11-12", "emisor": emisor, "rut_emisor": rut_emisor,
              "total": float(total)}
    if neto is not None:
        campos.update({"neto": float(neto), "iva": float(iva)})
    meta = PngInfo()
    meta.add_text("docuvali", json.dumps({"campos": campos, "campo_dudoso": campo_dudoso}))
    img.save(os.path.join(SALIDA, f"{nombre}.png"), pnginfo=meta)

    if xml_total is not None:
        tipo_dte = {"factura": 33, "boleta": 39}[tipo]
        xml = (f'<?xml version="1.0" encoding="ISO-8859-1"?>\n<DTE version="1.0"><Documento><Encabezado>'
               f"<IdDoc><TipoDTE>{tipo_dte}</TipoDTE><Folio>{folio}</Folio></IdDoc>"
               f"<Emisor><RUTEmisor>{rut_emisor.replace('.', '')}</RUTEmisor></Emisor>"
               f"<Totales><MntTotal>{int(xml_total)}</MntTotal></Totales>"
               f"</Encabezado></Documento></DTE>\n")
        with open(os.path.join(SALIDA, f"{nombre}.xml"), "w", encoding="utf-8") as f:
            f.write(xml)


if __name__ == "__main__":
    os.makedirs(SALIDA, exist_ok=True)
    documento("factura_correcta", "factura", "Comercial Ejemplo SpA", rut(76123456), 4521,
              100000, 19000, 119000, xml_total=119000)
    documento("factura_iva_incorrecto", "factura", "Distribuidora Ficticia Ltda.", rut(77654321, valido=False),
              8830, 250000, 45000, 295000, xml_total=297500, campo_dudoso="iva")
    documento("boleta_borrosa", "boleta", "Librería Demo SpA", rut(78111222), 120554,
              None, None, 15990, borroso=True, campo_dudoso="total")
    print("muestras creadas en", SALIDA, os.listdir(SALIDA))
