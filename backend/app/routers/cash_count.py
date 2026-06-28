from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from datetime import date
import json

from app.database import get_db
from app.models.cash_register import CashRegister
from app.models.payment import Payment
from app.models.expense import Expense
from app.models.cash_count import CashCount
from app.auth.dependencies import admin_only
from app.models.user import User
from pydantic import BaseModel

router = APIRouter(prefix="/api/cash-count", tags=["cash-count"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class CashCountCreate(BaseModel):
    denominaciones: dict          # {"100000": 3, "50000": 5, ...}
    total_contado: float
    observaciones: Optional[str] = None


# ── Helper: resumen financiero de la caja activa ─────────────────────────────

def _get_summary(db: Session, caja: CashRegister) -> dict:
    """Calcula ventas por método de pago para la caja activa."""
    pagos = db.query(Payment).filter(Payment.caja_id == caja.id).all()

    ventas_efectivo      = sum(p.monto for p in pagos if p.metodo == "efectivo")
    ventas_tarjeta       = sum(p.monto for p in pagos if p.metodo == "tarjeta")
    ventas_transferencia = sum(p.monto for p in pagos if p.metodo == "transferencia")
    total_ventas         = ventas_efectivo + ventas_tarjeta + ventas_transferencia

    # Egresos registrados en este turno
    egresos_todos = db.query(Expense).filter(Expense.caja_id == caja.id).all()
    egresos_efectivo      = sum(e.monto for e in egresos_todos if e.metodo_pago == "efectivo")
    egresos_tarjeta       = sum(e.monto for e in egresos_todos if e.metodo_pago == "tarjeta")
    egresos_transferencia = sum(e.monto for e in egresos_todos if e.metodo_pago == "transferencia")
    egresos_total         = sum(e.monto for e in egresos_todos)

    # Gastos del día (todos, para referencia en Finanzas)
    hoy = date.today()
    gastos_hoy = db.query(func.sum(Expense.monto)).filter(
        Expense.fecha == hoy
    ).scalar() or 0.0

    # Efectivo esperado = fondo + ventas efectivo − egresos en efectivo
    efectivo_esperado = caja.fondo_inicial + ventas_efectivo - egresos_efectivo

    return {
        "caja_id": caja.id,
        "apertura": caja.apertura.isoformat() if caja.apertura else None,
        "fondo_inicial": caja.fondo_inicial,
        "ventas_efectivo": ventas_efectivo,
        "ventas_tarjeta": ventas_tarjeta,
        "ventas_transferencia": ventas_transferencia,
        "total_ventas": total_ventas,
        "egresos_efectivo": egresos_efectivo,
        "egresos_tarjeta": egresos_tarjeta,
        "egresos_transferencia": egresos_transferencia,
        "egresos_total": egresos_total,
        "gastos_hoy": gastos_hoy,
        "efectivo_esperado": efectivo_esperado,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/summary")
def get_summary(
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    """Retorna el resumen financiero de la caja activa para el cuadre."""
    caja = db.query(CashRegister).filter(CashRegister.estado == "abierta").first()
    if not caja:
        raise HTTPException(404, "No hay caja abierta")
    return _get_summary(db, caja)


@router.post("")
def save_count(
    data: CashCountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """Guarda el resultado del cuadre de caja."""
    caja = db.query(CashRegister).filter(CashRegister.estado == "abierta").first()
    if not caja:
        raise HTTPException(404, "No hay caja abierta")

    summary = _get_summary(db, caja)
    diferencia = data.total_contado - summary["efectivo_esperado"]

    count = CashCount(
        caja_id=caja.id,
        usuario_id=current_user.id,
        denominaciones=json.dumps(data.denominaciones),
        total_contado=data.total_contado,
        total_esperado=summary["efectivo_esperado"],
        diferencia=diferencia,
        observaciones=data.observaciones,
    )
    db.add(count)
    db.commit()
    db.refresh(count)

    return {
        "id": count.id,
        "total_contado": count.total_contado,
        "total_esperado": count.total_esperado,
        "diferencia": count.diferencia,
        "created_at": count.created_at.isoformat() if count.created_at else None,
    }


@router.get("/history")
def get_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
):
    """Historial de cuadres guardados."""
    counts = (
        db.query(CashCount)
        .order_by(CashCount.created_at.desc())
        .limit(limit)
        .all()
    )
    result = []
    for c in counts:
        result.append({
            "id": c.id,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "usuario_nombre": c.usuario.nombre if c.usuario else "—",
            "total_contado": c.total_contado,
            "total_esperado": c.total_esperado,
            "diferencia": c.diferencia,
            "observaciones": c.observaciones,
            "denominaciones": json.loads(c.denominaciones or "{}"),
        })
    return result
