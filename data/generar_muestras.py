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
              campo_dudoso=None, ruido=False, detalle="Resmas papel carta (10 u.)", borroso_radio=4):
    img = Image.new("RGB", (900, 1100), "white")
    d = ImageDraw.Draw(img)
    titulo = {"factura": "FACTURA ELECTRÓNICA", "boleta": "BOLETA ELECTRÓNICA",
              "nota_credito": "NOTA DE CRÉDITO ELECT."}[tipo]
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
    d.text((50, 410), detalle, font=fuente(22), fill="black")
    d.text((650, 410), clp(neto or total), font=fuente(22), fill="black")
    y = 820
    if neto is not None:
        d.text((480, y), "MONTO NETO", font=fuente(24), fill="black"); d.text((680, y), clp(neto), font=fuente(24), fill="black"); y += 50
        d.text((480, y), "IVA 19%", font=fuente(24), fill="black"); d.text((680, y), clp(iva), font=fuente(24), fill="black"); y += 50
    d.text((480, y), "TOTAL", font=fuente(28), fill="black"); d.text((680, y), clp(total), font=fuente(28), fill="black")
    if ruido:  # foto tomada con celular: levemente girada y con grano
        import random
        random.seed(folio)
        px = img.load()
        for _ in range(60000):
            x, y = random.randrange(img.width), random.randrange(img.height)
            g = random.randint(150, 235)
            px[x, y] = (g, g, g)
        img = img.rotate(1.8, expand=False, fillcolor="white").filter(ImageFilter.GaussianBlur(1.2))
    if borroso:
        img = img.filter(ImageFilter.GaussianBlur(borroso_radio))

    campos = {"folio": str(folio), "fecha": "2026-11-12", "emisor": emisor, "rut_emisor": rut_emisor,
              "total": float(total)}
    if neto is not None:
        campos.update({"neto": float(neto), "iva": float(iva)})
    meta = PngInfo()
    meta.add_text("docuvali", json.dumps({"campos": campos, "campo_dudoso": campo_dudoso}))
    img.save(os.path.join(SALIDA, f"{nombre}.png"), pnginfo=meta)

    if xml_total is not None:
        tipo_dte = {"factura": 33, "boleta": 39, "nota_credito": 61}[tipo]
        xml = (f'<?xml version="1.0" encoding="ISO-8859-1"?>\n<DTE version="1.0"><Documento><Encabezado>'
               f"<IdDoc><TipoDTE>{tipo_dte}</TipoDTE><Folio>{folio}</Folio></IdDoc>"
               f"<Emisor><RUTEmisor>{rut_emisor.replace('.', '')}</RUTEmisor></Emisor>"
               f"<Totales><MntTotal>{int(xml_total)}</MntTotal></Totales>"
               f"</Encabezado></Documento></DTE>\n")
        with open(os.path.join(SALIDA, f"{nombre}.xml"), "w", encoding="utf-8") as f:
            f.write(xml)


MUESTRAS = [
    # (archivo, tipo, emisor, rut cuerpo, rut válido, folio, neto, iva, total, xml_total, opciones, descripción)
    ("factura_correcta", "factura", "Comercial Ejemplo SpA", 76123456, True, 4521, 100000, 19000, 119000, 119000, {}, "Todo cuadra"),
    ("factura_iva_incorrecto", "factura", "Distribuidora Ficticia Ltda.", 77654321, False, 8830, 250000, 45000, 295000, 297500,
     {"campo_dudoso": "iva"}, "IVA mal calculado y RUT inválido"),
    ("boleta_borrosa", "boleta", "Librería Demo SpA", 78111222, True, 120554, None, None, 15990, None,
     {"borroso": True, "campo_dudoso": "total"}, "Foto muy borrosa"),
    ("boleta_correcta", "boleta", "Minimarket Los Aromos SpA", 76543210, True, 88412, None, None, 12490, 12490, {}, "Boleta nítida con XML"),
    ("factura_monto_alto", "factura", "Constructora Andes Sur SpA", 76987123, True, 1502, 5000000, 950000, 5950000, 5950000,
     {"detalle": "Arriendo de maquinaria (1 mes)"}, "Monto alto, todo cuadra"),
    ("factura_rut_invalido", "factura", "Servicios Integrales Pacífico Ltda.", 76222333, False, 3310, 80000, 15200, 95200, 95200,
     {"detalle": "Mantención de equipos"}, "Solo el RUT es inválido"),
    ("factura_total_no_cuadra", "factura", "Ferretería El Roble SpA", 77111444, True, 9921, 300000, 57000, 375000, 357000,
     {"detalle": "Herramientas eléctricas", "campo_dudoso": "total"}, "Total distinto de neto + IVA"),
    ("factura_xml_distinto", "factura", "Imprenta Austral Ltda.", 76333888, True, 7045, 150000, 28500, 178500, 187500,
     {"detalle": "Impresión de catálogos"}, "El total no coincide con el XML del SII"),
    ("factura_sin_xml", "factura", "Café y Té Valparaíso SpA", 76777555, True, 2208, 45000, 8550, 53550, None,
     {"detalle": "Insumos de cafetería"}, "Correcta, pero sin XML para comparar"),
    ("nota_credito_correcta", "nota_credito", "Comercial Ejemplo SpA", 76123456, True, 512, 20000, 3800, 23800, 23800,
     {"detalle": "Devolución de 2 resmas"}, "Nota de crédito que cuadra"),
    ("factura_foto_celular", "factura", "Tecnología Norte SpA", 76444999, True, 6633, 420000, 79800, 499800, 499800,
     {"detalle": "Notebook de oficina", "ruido": True}, "Foto de celular inclinada, con grano"),
    ("factura_levemente_borrosa", "factura", "Agrícola Valle Central Ltda.", 77222111, True, 1194, 60000, 11400, 71400, 71400,
     {"detalle": "Semillas y fertilizantes", "borroso": True, "borroso_radio": 1.6}, "Algo desenfocada, datos correctos"),
    ("boleta_sin_xml_borrosa", "boleta", "Farmacia Barrio Sur SpA", 76888777, True, 300451, None, None, 8990, None,
     {"borroso": True, "borroso_radio": 2.5, "campo_dudoso": "total"}, "Boleta desenfocada y sin XML"),
]


if __name__ == "__main__":
    os.makedirs(SALIDA, exist_ok=True)
    indice = []
    for nombre, tipo, emisor, cuerpo, valido, folio, neto, iva, total, xml_total, op, desc in MUESTRAS:
        documento(nombre, tipo, emisor, rut(cuerpo, valido), folio, neto, iva, total, xml_total=xml_total, **op)
        indice.append({"archivo": nombre, "tipo": tipo, "descripcion": desc, "con_xml": xml_total is not None})
    with open(os.path.join(SALIDA, "muestras.json"), "w", encoding="utf-8") as f:
        json.dump(indice, f, ensure_ascii=False, indent=2)
    print(f"{len(indice)} muestras creadas en {SALIDA}")
