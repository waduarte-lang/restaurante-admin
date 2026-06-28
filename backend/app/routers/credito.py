from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional

from app.database import get_db
from app.models.credito import CreditoCliente, Credito, Abono
from app.schemas.credito import (
    CreditoClienteCreate, CreditoClienteUpdate, CreditoClienteOut,
    CreditoCreate, CreditoOut,
    AbonoCreate,
)
from app.auth.dependencies import get_current_user, admin_only

router = APIRouter(prefix="/api/credito", tags=["credito"])


# ─────────────────────────────────────────────────────────────────────────────
# Clientes de crédito
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/clientes", response_model=List[CreditoClienteOut])
def list_clientes(
    todos: bool = False,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(CreditoCliente)
    if not todos:
        q = q.filter(CreditoCliente.activo == True)
    clientes = q.order_by(CreditoCliente.nombre).all()

    result = []
    for c in clientes:
        deuda_rows = db.query(Credito).filter(
            Credito.cliente_id == c.id,
            Credito.estado.in_(["pendiente", "parcial"]),
        ).all()
        out = CreditoClienteOut.model_validate(c)
        out.total_deuda = round(sum(cr.saldo_pendiente for cr in deuda_rows), 2)
        result.append(out)
    return result


@router.post("/clientes", response_model=CreditoClienteOut)
def create_cliente(
    data: CreditoClienteCreate,
    db: Session = Depends(get_db),
    _=Depends(admin_only),
):
    c = CreditoCliente(**data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    out = CreditoClienteOut.model_validate(c)
    out.total_deuda = 0
    return out


@router.put("/clientes/{cliente_id}", response_model=CreditoClienteOut)
def update_cliente(
    cliente_id: int,
    data: CreditoClienteUpdate,
    db: Session = Depends(get_db),
    _=Depends(admin_only),
):
    c = db.query(CreditoCliente).filter(CreditoCliente.id == cliente_id).first()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    deuda_rows = db.query(Credito).filter(
        Credito.cliente_id == cliente_id,
        Credito.estado.in_(["pendiente", "parcial"]),
    ).all()
    out = CreditoClienteOut.model_validate(c)
    out.total_deuda = round(sum(cr.saldo_pendiente for cr in deuda_rows), 2)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Créditos
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/creditos", response_model=List[CreditoOut])
def list_creditos(
    cliente_id: Optional[int] = None,
    estado:     Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(Credito).options(
        joinedload(Credito.cliente),
        joinedload(Credito.abonos),
    )
    if cliente_id:
        q = q.filter(Credito.cliente_id == cliente_id)
    if estado:
        q = q.filter(Credito.estado == estado)
    creditos = q.order_by(Credito.fecha.desc()).all()

    result = []
    for cr in creditos:
        out = CreditoOut.model_validate(cr)
        out.cliente_nombre = cr.cliente.nombre if cr.cliente else ""
        result.append(out)
    return result


@router.post("/creditos", response_model=CreditoOut)
def create_credito(
    data: CreditoCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    c = db.query(CreditoCliente).filter(CreditoCliente.id == data.cliente_id).first()
    if not c:
        raise HTTPException(404, "Cliente de crédito no encontrado")

    cr = Credito(
        cliente_id=data.cliente_id,
        order_id=data.order_id,
        monto_total=data.monto_total,
        saldo_pendiente=data.monto_total,
        estado="pendiente",
        concepto=data.concepto,
        cajero_id=user.id,
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)

    out = CreditoOut.model_validate(cr)
    out.cliente_nombre = c.nombre
    out.abonos = []
    return out


@router.post("/creditos/{credito_id}/abonos", response_model=CreditoOut)
def add_abono(
    credito_id: int,
    data: AbonoCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    cr = db.query(Credito).options(
        joinedload(Credito.cliente),
        joinedload(Credito.abonos),
    ).filter(Credito.id == credito_id).first()

    if not cr:
        raise HTTPException(404, "Crédito no encontrado")
    if cr.estado == "pagado":
        raise HTTPException(400, "Este crédito ya está pagado")
    if data.monto <= 0:
        raise HTTPException(400, "El monto del abono debe ser mayor a 0")
    if data.monto > cr.saldo_pendiente + 0.01:
        raise HTTPException(
            400,
            f"El abono (${data.monto:,.0f}) supera el saldo pendiente (${cr.saldo_pendiente:,.0f})"
        )

    abono = Abono(
        credito_id=credito_id,
        monto=data.monto,
        metodo_pago=data.metodo_pago,
        observaciones=data.observaciones,
        cajero_id=user.id,
    )
    db.add(abono)

    cr.saldo_pendiente = max(0, round(cr.saldo_pendiente - data.monto, 2))
    cr.estado = "pagado" if cr.saldo_pendiente == 0 else "parcial"

    db.commit()
    db.refresh(cr)

    out = CreditoOut.model_validate(cr)
    out.cliente_nombre = cr.cliente.nombre if cr.cliente else ""
    return out


@router.get("/resumen")
def resumen(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Resumen general de cartera: total adeudado y desglose por cliente."""
    clientes = db.query(CreditoCliente).filter(CreditoCliente.activo == True).all()
    total_cartera = 0.0
    detalle = []
    for c in clientes:
        creditos = db.query(Credito).filter(
            Credito.cliente_id == c.id,
            Credito.estado.in_(["pendiente", "parcial"]),
        ).all()
        deuda = round(sum(cr.saldo_pendiente for cr in creditos), 2)
        if deuda > 0:
            total_cartera += deuda
            detalle.append({"cliente_id": c.id, "nombre": c.nombre, "deuda": deuda})
    return {
        "total_cartera": round(total_cartera, 2),
        "clientes": sorted(detalle, key=lambda x: -x["deuda"]),
    }
