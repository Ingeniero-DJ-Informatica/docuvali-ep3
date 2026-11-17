"""Mensajería entre servicios con RabbitMQ (patrón productor-consumidor + pub/sub).

- Cola durable `documentos.procesar`: la API publica, el worker consume.
- Cola `documentos.fallidos` (DLQ): recibe los mensajes rechazados tras fallar.
- Exchange fanout `docuvali.resultados`: el worker publica cada resultado y
  cualquier servicio puede suscribirse sin modificar a los demás.
"""
import json
import logging
import threading
import time

from . import config

log = logging.getLogger("docuvali.broker")


def _declarar(canal):
    canal.exchange_declare("docuvali.dlx", "fanout", durable=True)
    canal.queue_declare(config.COLA_FALLIDOS, durable=True)
    canal.queue_bind(config.COLA_FALLIDOS, "docuvali.dlx")
    canal.queue_declare(config.COLA_TRABAJOS, durable=True,
                        arguments={"x-dead-letter-exchange": "docuvali.dlx"})
    canal.exchange_declare(config.EXCHANGE_RESULTADOS, "fanout", durable=True)
    canal.queue_declare("documentos.auditoria", durable=True)
    canal.queue_bind("documentos.auditoria", config.EXCHANGE_RESULTADOS)


def conectar(url=None, intentos=30):
    import pika
    params = pika.URLParameters(url or config.RABBITMQ_URL)
    params.heartbeat = 60
    for i in range(intentos):
        try:
            con = pika.BlockingConnection(params)
            canal = con.channel()
            _declarar(canal)
            return con, canal
        except Exception as e:  # RabbitMQ todavía no está listo
            log.warning("RabbitMQ no disponible (%s), reintento %s/%s", e, i + 1, intentos)
            time.sleep(2)
    raise RuntimeError("No fue posible conectar con RabbitMQ")


class RabbitBroker:
    def __init__(self):
        self._lock = threading.Lock()
        self.con = self.canal = None

    def _asegurar(self):
        if self.con is None or self.con.is_closed:
            self.con, self.canal = conectar()

    def publicar_trabajo(self, mensaje: dict):
        import pika
        cuerpo = json.dumps(mensaje).encode()
        props = pika.BasicProperties(delivery_mode=2, content_type="application/json",
                                     message_id=mensaje["id"])
        with self._lock:
            for intento in range(2):
                try:
                    self._asegurar()
                    self.canal.basic_publish("", config.COLA_TRABAJOS, cuerpo, props)
                    return
                except Exception:
                    self.con = None
                    if intento:
                        raise

    def estado(self):
        try:
            with self._lock:
                self._asegurar()
                q = self.canal.queue_declare(config.COLA_TRABAJOS, passive=True)
                d = self.canal.queue_declare(config.COLA_FALLIDOS, passive=True)
            return {"conectado": True, "en_cola": q.method.message_count, "fallidos": d.method.message_count}
        except Exception as e:
            self.con = None
            return {"conectado": False, "error": str(e)}


class MemoriaBroker:
    """Para pruebas: procesa el mensaje de inmediato con el mismo pipeline."""

    def __init__(self, procesador=None):
        self.procesador = procesador
        self.publicados = []

    def publicar_trabajo(self, mensaje: dict):
        self.publicados.append(mensaje)
        if self.procesador:
            self.procesador(mensaje)

    def estado(self):
        return {"conectado": True, "en_cola": 0, "fallidos": 0, "modo": "memoria"}
