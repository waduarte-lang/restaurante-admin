"""
Cola de impresion termica — el servicio de Windows consulta y reporta resultados.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from ..database import get_db
from ..auth.dependencies import get_current_user, require_roles
from ..models.order import Order
from ..models.user import User
import sqlite3 as _sq
import os as _os

router = APIRouter(prefix="/api/print", tags=["print"])

_REPRINT_DB = _os.path.join(_os.path.dirname(__file__), '..', '..', 'reprint_queue.db')


def _rq_init():
    c = _sq.connect(_REPRINT_DB)
    # Si la tabla existe pero no tiene columna 'id', migrar
    cols = [r[1] for r in c.execute("PRAGMA table_info(queue)").fetchall()]
    if cols and 'id' not in cols:
        c.execute("ALTER TABLE queue RENAME TO queue_old")
        cols = []  # forzar recreacion
    if not cols:
        c.execute("""CREATE TABLE queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            comanda_numero TEXT,
            tipo TEXT,
            status TEXT DEFAULT 'pending',
            error_msg TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT
        )""")
        # Migrar datos viejos si existian
        try:
            c.execute("INSERT INTO queue (order_id, status, created_at) SELECT order_id, 'pending', COALESCE(ts, datetime('now')) FROM queue_old")
            c.execute("DROP TABLE queue_old")
        except Exception:
            pass
    # Normalizar registros sin status
    c.execute("UPDATE queue SET status='pending' WHERE status IS NULL")
    c.commit()
    c.close()


try:
    _rq_init()
except Exception:
    pass


# ── Diagnostico ───────────────────────────────────────────────────────────────

@router.get("/debug-orden/{order_id}")
def debug_orden(order_id: int, db: Session = Depends(get_db), por_numero: bool = False):
    q = db.query(Order)
    order = (
        q.filter(Order.comanda_numero == order_id).order_by(Order.id.desc()).first()
        if por_numero else
        q.filter(Order.id == order_id).first()
    )
    if not order:
        return {"error": "no encontrada"}
    return {
        "id": order.id,
        "comanda_numero": order.comanda_numero,
        "tipo": order.tipo,
        "cliente_nombre": order.cliente_nombre,
        "observaciones": order.observaciones,
    }


# ── Encolar impresion (llamado desde frontend) ────────────────────────────────

@router.post("/comanda/{order_id}")
def queue_print(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Encola una comanda para imprimir en el servicio local de Windows."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Comanda no encontrada")

    c = _sq.connect(_REPRINT_DB)
    # Si ya esta en cola como pending o printing, no duplicar
    existing = c.execute(
        "SELECT id FROM queue WHERE order_id=? AND status IN ('pending','printing')",
        (order_id,)
    ).fetchone()
    if not existing:
        # Si hay un error previo para esta orden, reactivarlo
        reactivated = c.execute(
            "UPDATE queue SET status='pending', error_msg=NULL, updated_at=datetime('now') "
            "WHERE order_id=? AND status='error'",
            (order_id,)
        ).rowcount
        if not reactivated:
            c.execute(
                "INSERT INTO queue (order_id, comanda_numero, tipo, status, created_at) "
                "VALUES (?,?,?,'pending',datetime('now'))",
                (order_id, str(order.comanda_numero), order.tipo)
            )
    c.commit()
    c.close()
    return {"ok": True, "comanda": order.comanda_numero}


# ── Para el servicio de Windows ───────────────────────────────────────────────

@router.get("/reprint-queue")
def reprint_queue():
    """
    Consultado por el servicio de impresion en Windows cada N segundos.
    Retorna pendientes y los marca como 'printing'.
    Formato: {reprint: [{id, order_id}, ...]}
    """
    c = _sq.connect(_REPRINT_DB)
    rows = c.execute(
        "SELECT id, order_id FROM queue WHERE status='pending' ORDER BY created_at"
    ).fetchall()
    if rows:
        ids = [r[0] for r in rows]
        c.execute(
            f"UPDATE queue SET status='printing', updated_at=datetime('now') "
            f"WHERE id IN ({','.join('?'*len(ids))})",
            ids
        )
        c.commit()
    c.close()
    return {"reprint": [{"id": r[0], "order_id": r[1]} for r in rows]}


class QueueStatusUpdate(BaseModel):
    status: str                   # 'done' | 'error'
    error_msg: Optional[str] = None


@router.patch("/queue/{queue_id}")
def update_queue_status(queue_id: int, data: QueueStatusUpdate):
    """Llamado por el servicio de Windows para reportar resultado."""
    c = _sq.connect(_REPRINT_DB)
    c.execute(
        "UPDATE queue SET status=?, error_msg=?, updated_at=datetime('now') WHERE id=?",
        (data.status, data.error_msg, queue_id)
    )
    c.commit()
    c.close()
    return {"ok": True}


# ── Gestion de cola (frontend) ────────────────────────────────────────────────

@router.get("/queue")
def list_queue(
    current_user: User = Depends(get_current_user),
):
    """Lista la cola — usado por el modulo de impresion en el frontend."""
    c = _sq.connect(_REPRINT_DB)
    rows = c.execute(
        "SELECT id, order_id, comanda_numero, tipo, status, error_msg, created_at, updated_at "
        "FROM queue WHERE status != 'done' ORDER BY created_at DESC LIMIT 100"
    ).fetchall()
    c.close()
    return [
        {
            "id": r[0], "order_id": r[1], "comanda_numero": r[2],
            "tipo": r[3], "status": r[4], "error_msg": r[5],
            "created_at": r[6], "updated_at": r[7],
        }
        for r in rows
    ]


@router.delete("/queue/{queue_id}")
def delete_queue_item(
    queue_id: int,
    current_user: User = Depends(get_current_user),
):
    """Elimina un item de la cola."""
    c = _sq.connect(_REPRINT_DB)
    c.execute("DELETE FROM queue WHERE id=?", (queue_id,))
    c.commit()
    c.close()
    return {"ok": True}


@router.post("/queue/{queue_id}/retry")
def retry_queue_item(
    queue_id: int,
    current_user: User = Depends(get_current_user),
):
    """Reintenta imprimir un item con error."""
    c = _sq.connect(_REPRINT_DB)
    c.execute(
        "UPDATE queue SET status='pending', error_msg=NULL, updated_at=datetime('now') WHERE id=?",
        (queue_id,)
    )
    c.commit()
    c.close()
    return {"ok": True}
