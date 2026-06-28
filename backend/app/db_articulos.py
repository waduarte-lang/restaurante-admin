"""
Base de datos local SQLite para estadísticas de artículos.
Archivo: backend/produccion_stats.db

Se actualiza llamando a sync_articulos_stats() o vía el endpoint
POST /api/produccion/articulos/sync

Cualquier dashboard externo puede conectarse directamente a este archivo
con cualquier driver SQLite (Python sqlite3, ODBC, DBeaver, Power BI, etc.)
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "produccion_stats.db")

CREATE_DDL = """
CREATE TABLE IF NOT EXISTS articulo_stats (
    id                   INTEGER PRIMARY KEY,
    product_name         TEXT,
    sku                  TEXT,
    color                TEXT,
    peso_nominal_g       REAL,
    ciclo_teorico_s      REAL,
    ordenes_terminadas   INTEGER,
    uds_totales          INTEGER,
    uds_defectuosas      INTEGER,
    tasa_defecto_pct     REAL,
    ultima_produccion    TEXT,
    seg_real_por_pieza   REAL,
    eficiencia_ciclo_pct REAL,
    g_resina_por_pieza   REAL,
    g_master_por_pieza   REAL,
    delta_material_pct   REAL,
    actualizado_en       TEXT
);

CREATE TABLE IF NOT EXISTS sync_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ejecutado  TEXT,
    filas      INTEGER,
    duracion_s REAL,
    error      TEXT
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript(CREATE_DDL)


def upsert_rows(rows: list[dict], duracion: float):
    ts = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute("DELETE FROM articulo_stats")
        conn.executemany("""
            INSERT INTO articulo_stats (
                id, product_name, sku, color,
                peso_nominal_g, ciclo_teorico_s,
                ordenes_terminadas, uds_totales, uds_defectuosas, tasa_defecto_pct,
                ultima_produccion,
                seg_real_por_pieza, eficiencia_ciclo_pct,
                g_resina_por_pieza, g_master_por_pieza, delta_material_pct,
                actualizado_en
            ) VALUES (
                :id, :product_name, :sku, :color,
                :peso_nominal, :ciclo_teorico,
                :ordenes_terminadas, :uds_totales, :uds_defectuosas, :tasa_defecto_pct,
                :ultima_produccion,
                :seg_real_por_pieza, :eficiencia_ciclo_pct,
                :g_resina_por_pieza, :g_master_por_pieza, :delta_material_pct,
                :ts
            )
        """, [{**r, "ts": ts} for r in rows])
        conn.execute(
            "INSERT INTO sync_log (ejecutado, filas, duracion_s) VALUES (?, ?, ?)",
            (ts, len(rows), round(duracion, 2))
        )
        conn.commit()


def query_all() -> list[dict]:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM articulo_stats ORDER BY uds_totales DESC")
        return [dict(r) for r in cur.fetchall()]


def last_sync() -> dict | None:
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 1")
        row = cur.fetchone()
        return dict(row) if row else None


init_db()
