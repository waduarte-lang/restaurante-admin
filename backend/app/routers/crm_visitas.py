from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.auth.dependencies import require_roles
from app.models.user import User
from app.models.visita import Visita
from app.models.crm_cliente import CRMCliente
from app.schemas.crm import VisitaCreate, VisitaUpdate, VisitaOut
from typing import List, Optional

router = APIRouter(prefix="/api/crm/visitas", tags=["CRM - Visitas"])

_ROLES = ("admin", "asesor", "gerente")


def _enrich(v: Visita) -> dict:
    d = {col.name: getattr(v, col.name) for col in v.__table__.columns}
    d["cliente_nombre"] = v.cliente.nombre if v.cliente else None
    d["asesor_nombre"] = v.asesor.nombre if v.asesor else None
    return d


@router.get("/", response_model=List[VisitaOut])
def listar_visitas(
    cliente_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    query = db.query(Visita).options(joinedload(Visita.cliente), joinedload(Visita.asesor))
    if current_user.rol == "asesor":
        query = query.filter(Visita.asesor_id == current_user.id)
    if cliente_id:
        query = query.filter(Visita.cliente_id == cliente_id)
    visitas = query.order_by(Visita.fecha_visita.desc()).all()
    return [_enrich(v) for v in visitas]


@router.post("/", response_model=VisitaOut)
def crear_visita(
    data: VisitaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    cliente = db.query(CRMCliente).filter(CRMCliente.id == data.cliente_id).first()
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")
    if current_user.rol == "asesor" and cliente.asesor_id != current_user.id:
        raise HTTPException(403, "Acceso denegado")
    v = Visita(**data.model_dump(), asesor_id=current_user.id)
    db.add(v)
    db.commit()
    db.refresh(v)
    return _enrich(v)


@router.put("/{visita_id}", response_model=VisitaOut)
def actualizar_visita(
    visita_id: int,
    data: VisitaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    v = db.query(Visita).filter(Visita.id == visita_id).first()
    if not v:
        raise HTTPException(404, "Visita no encontrada")
    if current_user.rol == "asesor" and v.asesor_id != current_user.id:
        raise HTTPException(403, "Acceso denegado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(v, field, value)
    db.commit()
    db.refresh(v)
    return _enrich(v)


@router.delete("/{visita_id}")
def eliminar_visita(
    visita_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    v = db.query(Visita).filter(Visita.id == visita_id).first()
    if not v:
        raise HTTPException(404, "Visita no encontrada")
    if current_user.rol == "asesor" and v.asesor_id != current_user.id:
        raise HTTPException(403, "Acceso denegado")
    db.delete(v)
    db.commit()
    return {"ok": True}
