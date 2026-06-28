import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date

from app.database import get_db
from app.auth.dependencies import require_roles
from app.models.user import User
from app.models.tarea import Tarea
from app.models.crm_cliente import CRMCliente
from app.schemas.crm import TareaCreate, TareaUpdate, TareaOut

router = APIRouter(prefix="/api/crm/tareas", tags=["CRM - Tareas"])

_ROLES = ("admin", "asesor", "gerente")

ETAPAS = ["prospecto", "contactado", "visita_agendada", "propuesta", "negociacion", "cumplido"]


def _enrich(t: Tarea) -> dict:
    d = {col.name: getattr(t, col.name) for col in t.__table__.columns}
    # Deserializar actividades de JSON
    if d["actividades"]:
        try:
            d["actividades"] = json.loads(d["actividades"])
        except Exception:
            d["actividades"] = [d["actividades"]]
    else:
        d["actividades"] = []
    d["cliente_nombre"] = t.cliente.nombre if t.cliente else None
    return d


@router.get("/", response_model=List[TareaOut])
def listar_tareas(
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    etapa: Optional[str] = None,
    cliente_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    query = db.query(Tarea)
    if current_user.rol == "asesor":
        query = query.filter(Tarea.asesor_id == current_user.id)
    if etapa:
        query = query.filter(Tarea.etapa == etapa)
    if cliente_id:
        query = query.filter(Tarea.cliente_id == cliente_id)
    if fecha_desde:
        query = query.filter(Tarea.fecha_inicio >= datetime.combine(fecha_desde, datetime.min.time()))
    if fecha_hasta:
        query = query.filter(Tarea.fecha_inicio <= datetime.combine(fecha_hasta, datetime.max.time()))
    tareas = query.order_by(Tarea.fecha_inicio.nullslast(), Tarea.created_at.desc()).all()
    return [_enrich(t) for t in tareas]


@router.get("/kanban")
def kanban_tareas(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    """Devuelve tareas agrupadas por etapa para el tablero Kanban."""
    query = db.query(Tarea)
    if current_user.rol == "asesor":
        query = query.filter(Tarea.asesor_id == current_user.id)
    tareas = query.order_by(Tarea.created_at.desc()).all()
    enriched = [_enrich(t) for t in tareas]
    grouped = {etapa: [] for etapa in ETAPAS}
    for t in enriched:
        key = t["etapa"] if t["etapa"] in grouped else "prospecto"
        grouped[key].append(t)
    return grouped


@router.post("/", response_model=TareaOut)
def crear_tarea(
    data: TareaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    if data.cliente_id:
        c = db.query(CRMCliente).filter(CRMCliente.id == data.cliente_id).first()
        if not c:
            raise HTTPException(404, "Cliente no encontrado")
        if current_user.rol == "asesor" and c.asesor_id != current_user.id:
            raise HTTPException(403, "Acceso denegado")

    actividades_json = json.dumps(data.actividades or [], ensure_ascii=False)
    t = Tarea(
        asesor_id=current_user.id,
        cliente_id=data.cliente_id,
        titulo=data.titulo,
        actividades=actividades_json,
        duracion_minutos=data.duracion_minutos,
        que_llevar=data.que_llevar,
        fecha_inicio=data.fecha_inicio,
        etapa=data.etapa if data.etapa in ETAPAS else "prospecto",
        color=data.color,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _enrich(t)


@router.put("/{tarea_id}", response_model=TareaOut)
def actualizar_tarea(
    tarea_id: int,
    data: TareaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    t = db.query(Tarea).filter(Tarea.id == tarea_id).first()
    if not t:
        raise HTTPException(404, "Tarea no encontrada")
    if current_user.rol == "asesor" and t.asesor_id != current_user.id:
        raise HTTPException(403, "Acceso denegado")

    update_data = data.model_dump(exclude_unset=True)

    if "actividades" in update_data:
        update_data["actividades"] = json.dumps(update_data["actividades"] or [], ensure_ascii=False)
    if "etapa" in update_data and update_data["etapa"] not in ETAPAS:
        raise HTTPException(400, f"Etapa inválida. Válidas: {ETAPAS}")

    for field, value in update_data.items():
        setattr(t, field, value)

    db.commit()
    db.refresh(t)
    return _enrich(t)


@router.delete("/{tarea_id}")
def eliminar_tarea(
    tarea_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    t = db.query(Tarea).filter(Tarea.id == tarea_id).first()
    if not t:
        raise HTTPException(404, "Tarea no encontrada")
    if current_user.rol == "asesor" and t.asesor_id != current_user.id:
        raise HTTPException(403, "Acceso denegado")
    db.delete(t)
    db.commit()
    return {"ok": True}
