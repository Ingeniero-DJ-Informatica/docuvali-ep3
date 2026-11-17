"""Persistencia de documentos y resultados (SQLite en un volumen Docker)."""
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone

from . import config

_lock = threading.Lock()

ESQUEMA = """
CREATE TABLE IF NOT EXISTS documentos (
    id TEXT PRIMARY KEY,
    creado TEXT NOT NULL,
    actualizado TEXT NOT NULL,
    estado TEXT NOT NULL,              -- en_cola | procesando | listo | error
    tipo_documento TEXT NOT NULL,
    nombre_archivo TEXT,
    cliente TEXT,
    resultado TEXT,                    -- JSON
    error TEXT,
    ms_extraccion REAL, ms_modelo REAL, ms_total REAL
);
CREATE INDEX IF NOT EXISTS idx_creado ON documentos(creado);
"""


def _ahora():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def conectar(ruta=None):
    ruta = ruta or config.DB_PATH
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    con = sqlite3.connect(ruta, check_same_thread=False, timeout=15, isolation_level=None)  # autocommit
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")
    with _lock:
        for intento in range(5):
            try:
                con.execute("PRAGMA journal_mode=WAL")
                con.executescript(ESQUEMA)
                break
            except sqlite3.OperationalError:
                time.sleep(0.5 * (intento + 1))
    return con


class Repositorio:
    def __init__(self, ruta=None):
        self.con = conectar(ruta)

    def crear(self, doc_id, tipo, nombre_archivo, cliente):
        with _lock:
            self.con.execute(
                "INSERT INTO documentos (id, creado, actualizado, estado, tipo_documento, nombre_archivo, cliente)"
                " VALUES (?,?,?,?,?,?,?)", (doc_id, _ahora(), _ahora(), "en_cola", tipo, nombre_archivo, cliente))

    def actualizar(self, doc_id, **campos):
        if "resultado" in campos and not isinstance(campos["resultado"], str):
            campos["resultado"] = json.dumps(campos["resultado"], ensure_ascii=False)
        campos["actualizado"] = _ahora()
        sets = ", ".join(f"{k}=?" for k in campos)
        with _lock:
            self.con.execute(f"UPDATE documentos SET {sets} WHERE id=?", (*campos.values(), doc_id))

    @staticmethod
    def _fila(f):
        if f is None:
            return None
        d = dict(f)
        d["resultado"] = json.loads(d["resultado"]) if d["resultado"] else None
        return d

    def _consultar(self, sql, params=()):
        with _lock:  # una conexión compartida entre hilos: un uso a la vez
            return self.con.execute(sql, params).fetchall()

    def obtener(self, doc_id):
        filas = self._consultar("SELECT * FROM documentos WHERE id=?", (doc_id,))
        return self._fila(filas[0]) if filas else None

    def listar(self, limite=50):
        return [self._fila(f) for f in self._consultar("SELECT * FROM documentos ORDER BY creado DESC LIMIT ?", (limite,))]

    def resumen(self):
        filas = self._consultar("SELECT estado, resultado, ms_total FROM documentos")
        total = len(filas)
        listos = [f for f in filas if f["estado"] == "listo"]
        decisiones = [json.loads(f["resultado"])["prediccion"]["decision"] for f in listos if f["resultado"]]
        tiempos = sorted(f["ms_total"] for f in listos if f["ms_total"] is not None)

        def pct(p):
            return tiempos[min(int(len(tiempos) * p), len(tiempos) - 1)] if tiempos else None

        return {
            "documentos_total": total,
            "procesados": len(listos),
            "en_cola": sum(f["estado"] in ("en_cola", "procesando") for f in filas),
            "con_error": sum(f["estado"] == "error" for f in filas),
            "aprobados_automatico": decisiones.count("APROBADO_AUTOMATICO"),
            "revision_humana": decisiones.count("REVISION_HUMANA"),
            "pct_automatico": round(decisiones.count("APROBADO_AUTOMATICO") / len(decisiones), 4) if decisiones else None,
            "ms_procesamiento_p50": pct(0.50),
            "ms_procesamiento_p95": pct(0.95),
        }
