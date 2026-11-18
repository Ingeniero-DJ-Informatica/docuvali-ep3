"""Procesamiento de un documento: OCR -> variables -> modelo -> resultado."""
import logging
import os
import time

from . import config
from .features import construir
from .predictor import medir

log = logging.getLogger("docuvali.pipeline")


REGLAS_OBLIGATORIAS = {
    "rut_valido": "Regla obligatoria: el RUT del emisor no es válido",
    "total_cuadra": "Regla obligatoria: el total no cuadra con neto + IVA",
}


def aplicar_reglas(prediccion: dict, variables: dict) -> dict:
    """Barrera de seguridad sobre el modelo: ciertos errores tributarios siempre van a revisión,
    aunque el modelo los considere de bajo riesgo."""
    fallas = [texto for campo, texto in REGLAS_OBLIGATORIAS.items() if variables.get(campo) == 0]
    if not fallas or prediccion["decision"] == "REVISION_HUMANA":
        return prediccion
    p = dict(prediccion)
    p["decision"] = "REVISION_HUMANA"
    p["confianza_decision"] = 1.0
    p["regla_aplicada"] = fallas
    p["razones"] = [{"variable": "regla", "descripcion": f, "valor": 0, "aporte": 9.99,
                     "efecto": "fuerza la revisión"} for f in fallas] + p.get("razones", [])[:2]
    return p


class Procesador:
    def __init__(self, repo, extractor, predictor):
        self.repo, self.extractor, self.predictor = repo, extractor, predictor

    def __call__(self, mensaje: dict) -> dict:
        doc_id = mensaje["id"]
        t0 = time.perf_counter()
        self.repo.actualizar(doc_id, estado="procesando")
        try:
            if mensaje.get("variables"):           # entrada ya estructurada (JSON)
                variables, extraccion, ms_ext = mensaje["variables"], None, 0.0
            else:                                    # entrada imagen -> OCR
                with open(os.path.join(config.UPLOAD_DIR, doc_id), "rb") as f:
                    contenido = f.read()
                xml = None
                ruta_xml = os.path.join(config.UPLOAD_DIR, f"{doc_id}.xml")
                if os.path.exists(ruta_xml):
                    with open(ruta_xml, encoding="utf-8", errors="ignore") as f:
                        xml = f.read()
                t1 = time.perf_counter()
                extraccion = self.extractor.extraer(contenido)
                ms_ext = round((time.perf_counter() - t1) * 1000, 1)
                variables = construir(extraccion, mensaje["tipo_documento"], xml)

            prediccion, ms_mod = medir(self.predictor, variables)
            prediccion = aplicar_reglas(prediccion, variables)
            ms_total = round((time.perf_counter() - t0) * 1000, 1)
            resultado = {"extraccion": extraccion, "variables": variables, "prediccion": prediccion,
                         "motor_modelo": self.predictor.nombre}
            self.repo.actualizar(doc_id, estado="listo", resultado=resultado,
                                 ms_extraccion=ms_ext, ms_modelo=ms_mod, ms_total=ms_total)
            log.info("documento=%s decision=%s prob=%.3f ms_ocr=%s ms_modelo=%s ms_total=%s", doc_id,
                     prediccion["decision"], prediccion["probabilidad_error"], ms_ext, ms_mod, ms_total)
            return resultado
        except Exception as e:
            log.exception("documento=%s error=%s", doc_id, e)
            self.repo.actualizar(doc_id, estado="error", error=str(e)[:500])
            raise
