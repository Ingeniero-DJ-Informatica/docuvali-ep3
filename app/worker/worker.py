"""Worker de DocuVali: consume la cola de RabbitMQ y procesa cada documento.

Cada mensaje se confirma (ack) solo después de guardar el resultado. Si falla,
se reintenta hasta 3 veces; luego va a la cola de fallidos (DLQ).
"""
import json
import logging

import pika

from app.common import config
from app.common.broker import conectar
from app.common.extractor import crear_extractor
from app.common.pipeline import Procesador
from app.common.predictor import crear_predictor
from app.common.storage import Repositorio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("docuvali.worker")
MAX_INTENTOS = 3


def main():
    procesar = Procesador(Repositorio(), crear_extractor(), crear_predictor())
    con, canal = conectar()
    canal.basic_qos(prefetch_count=1)  # un documento a la vez por worker
    log.info("worker listo: extractor=%s modelo=%s", config.EXTRACTOR, config.PREDICTOR)

    def al_recibir(ch, metodo, props, cuerpo):
        mensaje = json.loads(cuerpo)
        intento = int((props.headers or {}).get("x-intento", 1))
        try:
            resultado = procesar(mensaje)
            ch.basic_publish(config.EXCHANGE_RESULTADOS, "", json.dumps(
                {"id": mensaje["id"], "decision": resultado["prediccion"]["decision"],
                 "probabilidad_error": resultado["prediccion"]["probabilidad_error"]}).encode(),
                pika.BasicProperties(content_type="application/json", delivery_mode=2))
            ch.basic_ack(metodo.delivery_tag)
        except Exception as e:
            if intento < MAX_INTENTOS:
                log.warning("documento=%s fallo intento %s: %s (reintento)", mensaje.get("id"), intento, e)
                ch.basic_publish("", config.COLA_TRABAJOS, cuerpo, pika.BasicProperties(
                    delivery_mode=2, content_type="application/json", headers={"x-intento": intento + 1}))
                ch.basic_ack(metodo.delivery_tag)
            else:
                log.error("documento=%s enviado a DLQ tras %s intentos", mensaje.get("id"), intento)
                ch.basic_reject(metodo.delivery_tag, requeue=False)

    canal.basic_consume(config.COLA_TRABAJOS, al_recibir)
    canal.start_consuming()


if __name__ == "__main__":
    main()
