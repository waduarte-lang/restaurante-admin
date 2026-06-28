from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import extract
from app.database import get_db
from app.auth.dependencies import require_roles
from app.models.user import User
from app.models.calendario_evento import CalendarioEvento
from app.models.crm_cliente import CRMCliente
from app.schemas.crm import EventoCreate, EventoUpdate, EventoOut
from typing import List, Optional
from datetime import datetime

router = APIRouter(prefix="/api/crm/calendario", tags=["CRM - Calendario"])

_ROLES = ("admin", "asesor", "gerente")


def _enrich(e: CalendarioEvento) -> dict:
    d = {col.name: getattr(e, col.name) for col in e.__table__.columns}
    d["cliente_nombre"] = e.cliente.nombre if e.cliente else None
    return d


@router.get("/", response_model=List[EventoOut])
def listar_eventos(
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    query = db.query(CalendarioEvento)
    if current_user.rol == "asesor":
        query = query.filter(CalendarioEvento.asesor_id == current_user.id)
    if year:
        query = query.filter(extract("year", CalendarioEvento.fecha_inicio) == year)
    if month:
        query = query.filter(extract("month", CalendarioEvento.fecha_inicio) == month)
    eventos = query.order_by(CalendarioEvento.fecha_inicio).all()
    return [_enrich(e) for e in eventos]


@router.post("/", response_model=EventoOut)
def crear_evento(
    data: EventoCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    if data.cliente_id:
        cliente = db.query(CRMCliente).filter(CRMCliente.id == data.cliente_id).first()
        if not cliente:
            raise HTTPException(404, "Cliente no encontrado")
        if current_user.rol == "asesor" and cliente.asesor_id != current_user.id:
            raise HTTPException(403, "Acceso denegado")
    e = CalendarioEvento(**data.model_dump(), asesor_id=current_user.id)
    db.add(e)
    db.commit()
    db.refresh(e)
    return _enrich(e)


@router.put("/{evento_id}", response_model=EventoOut)
def actualizar_evento(
    evento_id: int,
    data: EventoUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    e = db.query(CalendarioEvento).filter(CalendarioEvento.id == evento_id).first()
    if not e:
        raise HTTPException(404, "Evento no encontrado")
    if current_user.rol == "asesor" and e.asesor_id != current_user.id:
        raise HTTPException(403, "Acceso denegado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(e, field, value)
    db.commit()
    db.refresh(e)
    return _enrich(e)


@router.delete("/{evento_id}")
def eliminar_evento(
    evento_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    e = db.query(CalendarioEvento).filter(CalendarioEvento.id == evento_id).first()
    if not e:
        raise HTTPException(404, "Evento no encontrado")
    if current_user.rol == "asesor" and e.asesor_id != current_user.id:
        raise HTTPException(403, "Acceso denegado")
    db.delete(e)
    db.commit()
    return {"ok": True}
