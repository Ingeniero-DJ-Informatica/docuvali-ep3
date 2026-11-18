"""API REST de DocuVali (FastAPI). Documentación Swagger en /docs y OpenAPI en /openapi.json."""
import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from typing import Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from app.common import config
from app.common.storage import Repositorio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("docuvali.api")

TipoDoc = Literal["factura", "boleta", "nota_credito"]
TIPOS_ARCHIVO = {"image/png", "image/jpeg", "application/pdf"}


class Variables(BaseModel):
    """Variables de un documento ya extraído (entrada directa al modelo)."""
    tipo_documento: TipoDoc = "factura"
    calidad_imagen: float = Field(ge=0, le=1, examples=[0.85])
    confianza_ocr_media: float = Field(ge=0, le=1, examples=[0.93])
    confianza_ocr_min: float = Field(ge=0, le=1, examples=[0.81])
    campos_detectados: float = Field(ge=0, le=1, examples=[1.0])
    rut_valido: int = Field(ge=0, le=1, examples=[1])
    iva_cuadra: int = Field(ge=0, le=1, examples=[1])
    total_cuadra: int = Field(ge=0, le=1, examples=[1])
    coincide_xml: int = Field(ge=0, le=1, examples=[1])
    monto_total: float = Field(ge=0, examples=[119000])


class Aceptado(BaseModel):
    id: str
    estado: str
    consultar_en: str


api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="Clave de acceso del cliente")


class LimitadorTasa:
    """Ventana deslizante de 60 s por clave de API (rate limiting)."""

    def __init__(self, limite_por_min):
        self.limite = limite_por_min
        self.registros = defaultdict(deque)

    def permitir(self, clave):
        ahora = time.monotonic()
        q = self.registros[clave]
        while q and ahora - q[0] > 60:
            q.popleft()
        if len(q) >= self.limite:
            return False, 0
        q.append(ahora)
        return True, self.limite - len(q)


def crear_app(repo=None, broker=None, predictor=None, limite_por_min=None):
    app = FastAPI(
        title="DocuVali API",
        version="3.0.0",
        description="Extracción y validación inteligente de documentos tributarios chilenos. "
                    "Los documentos se procesan de forma asíncrona (RabbitMQ) con Amazon Textract "
                    "y un modelo de decisión desplegado en Amazon SageMaker.",
    )
    repo = repo or Repositorio()
    if broker is None:
        from app.common.broker import RabbitBroker
        broker = RabbitBroker()
    if predictor is None:
        from app.common.predictor import crear_predictor
        predictor = crear_predictor()
    limitador = LimitadorTasa(limite_por_min or config.RATE_LIMIT_POR_MIN)
    app.state.repo, app.state.broker, app.state.predictor = repo, broker, predictor
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)

    @app.middleware("http")
    async def registrar(request: Request, call_next):
        t0 = time.perf_counter()
        respuesta = await call_next(request)
        ms = (time.perf_counter() - t0) * 1000
        respuesta.headers["X-Response-Time-ms"] = f"{ms:.1f}"
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.url.path != "/health":
            log.info(json.dumps({"metodo": request.method, "ruta": request.url.path,
                                 "estado": respuesta.status_code, "ms": round(ms, 1)}))
        return respuesta

    def autenticar(clave: str | None = Depends(api_key_header)):
        if not clave or clave not in config.API_KEYS:
            raise HTTPException(401, "Clave de API inválida o ausente (encabezado X-API-Key)")
        ok, restantes = limitador.permitir(clave)
        if not ok:
            raise HTTPException(429, f"Límite de {limitador.limite} solicitudes por minuto excedido",
                                headers={"Retry-After": "60"})
        return clave

    @app.get("/health", tags=["Sistema"], summary="Estado del servicio (usado por el balanceador)")
    def health():
        return {"estado": "ok", "servicio": "docuvali-api", "modelo": predictor.nombre, "extractor": config.EXTRACTOR}

    @app.post("/api/v1/documentos", status_code=202, response_model=Aceptado, tags=["Documentos"],
              summary="Sube una factura o boleta (imagen/PDF) para procesarla")
    async def subir(archivo: UploadFile = File(...), tipo_documento: TipoDoc = Form("factura"),
                    xml_dte: UploadFile | None = File(None), cliente: str = Depends(autenticar)):
        if archivo.content_type not in TIPOS_ARCHIVO:
            raise HTTPException(415, f"Formato no soportado: {archivo.content_type}")
        contenido = await archivo.read()
        if len(contenido) > config.MAX_ARCHIVO_MB * 1024 * 1024:
            raise HTTPException(413, f"El archivo supera {config.MAX_ARCHIVO_MB} MB")
        doc_id = uuid.uuid4().hex[:12]
        with open(os.path.join(config.UPLOAD_DIR, doc_id), "wb") as f:
            f.write(contenido)
        if xml_dte is not None:
            with open(os.path.join(config.UPLOAD_DIR, f"{doc_id}.xml"), "wb") as f:
                f.write(await xml_dte.read())
        repo.crear(doc_id, tipo_documento, archivo.filename, cliente[:6])
        broker.publicar_trabajo({"id": doc_id, "tipo_documento": tipo_documento})
        return Aceptado(id=doc_id, estado="en_cola", consultar_en=f"/api/v1/documentos/{doc_id}")

    @app.post("/api/v1/documentos/estructurado", status_code=202, response_model=Aceptado, tags=["Documentos"],
              summary="Envía un documento ya extraído (variables) a la cola de procesamiento")
    def subir_estructurado(v: Variables, cliente: str = Depends(autenticar)):
        doc_id = uuid.uuid4().hex[:12]
        repo.crear(doc_id, v.tipo_documento, None, cliente[:6])
        broker.publicar_trabajo({"id": doc_id, "tipo_documento": v.tipo_documento, "variables": v.model_dump()})
        return Aceptado(id=doc_id, estado="en_cola", consultar_en=f"/api/v1/documentos/{doc_id}")

    @app.get("/api/v1/documentos/{doc_id}", tags=["Documentos"], summary="Estado y resultado de un documento")
    def obtener(doc_id: str, _: str = Depends(autenticar)):
        doc = repo.obtener(doc_id)
        if not doc:
            raise HTTPException(404, "Documento no encontrado")
        return doc

    @app.get("/api/v1/documentos", tags=["Documentos"], summary="Últimos documentos procesados")
    def listar(limite: int = 50, _: str = Depends(autenticar)):
        return repo.listar(min(max(limite, 1), 500))

    @app.post("/api/v1/predicciones", tags=["Modelo"],
              summary="Predicción en tiempo real del modelo (llamada síncrona al endpoint de SageMaker)")
    def predecir(v: Variables, _: str = Depends(autenticar)):
        t0 = time.perf_counter()
        try:
            r = predictor.predecir(v.model_dump())
        except Exception as e:
            log.exception("error del modelo")
            raise HTTPException(503, f"El modelo no está disponible: {e}")
        return {**r, "motor_modelo": predictor.nombre, "ms_modelo": round((time.perf_counter() - t0) * 1000, 1)}

    @app.get("/api/v1/metricas", tags=["Sistema"], summary="Indicadores para el dashboard")
    def metricas(_: str = Depends(autenticar)):
        modelo = None
        if os.path.exists(config.METRICS_JSON):
            with open(config.METRICS_JSON) as f:
                modelo = json.load(f)
        return {"operacion": repo.resumen(), "cola": broker.estado(), "modelo": modelo}

    @app.exception_handler(Exception)
    async def error_general(request: Request, exc: Exception):
        log.exception("error no controlado")
        return JSONResponse(status_code=500, content={"detail": "Error interno"})

    return app


def _app_produccion():
    return crear_app()


app = _app_produccion() if os.environ.get("DOCUVALI_NO_AUTOAPP") != "1" else None
