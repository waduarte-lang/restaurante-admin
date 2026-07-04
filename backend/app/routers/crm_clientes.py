from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.auth.dependencies import get_current_user, require_roles
from app.models.user import User
from app.models.crm_cliente import CRMCliente
from app.schemas.crm import CRMClienteCreate, CRMClienteUpdate, CRMClienteOut
from typing import List, Optional

router = APIRouter(prefix="/api/crm/clientes", tags=["CRM - Clientes"])

_ROLES = ("admin", "asesor", "gerente")


def _enrich(c: CRMCliente) -> dict:
    d = {col.name: getattr(c, col.name) for col in c.__table__.columns}
    d["asesor_nombre"] = c.asesor.nombre if c.asesor else None
    return d


@router.get("/", response_model=List[CRMClienteOut])
def listar_clientes(
    q: Optional[str] = None,
    asesor_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    query = db.query(CRMCliente).options(joinedload(CRMCliente.asesor)).filter(CRMCliente.activo == True)
    if current_user.rol == "asesor":
        query = query.filter(CRMCliente.asesor_id == current_user.id)
    elif asesor_id:
        query = query.filter(CRMCliente.asesor_id == asesor_id)
    if q:
        query = query.filter(
            CRMCliente.nombre.ilike(f"%{q}%") | CRMCliente.nit.ilike(f"%{q}%")
        )
    clientes = query.order_by(CRMCliente.nombre).all()
    return [_enrich(c) for c in clientes]


@router.get("/{cliente_id}", response_model=CRMClienteOut)
def detalle_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    c = db.query(CRMCliente).options(joinedload(CRMCliente.asesor)).filter(CRMCliente.id == cliente_id).first()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    if current_user.rol == "asesor" and c.asesor_id != current_user.id:
        raise HTTPException(403, "Acceso denegado")
    return _enrich(c)


@router.post("/", response_model=CRMClienteOut)
def crear_cliente(
    data: CRMClienteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    asesor_id = data.asesor_id
    if current_user.rol == "asesor":
        asesor_id = current_user.id
    c = CRMCliente(**data.model_dump(exclude={"asesor_id"}), asesor_id=asesor_id)
    db.add(c)
    db.commit()
    db.refresh(c)
    return _enrich(c)


@router.put("/{cliente_id}", response_model=CRMClienteOut)
def actualizar_cliente(
    cliente_id: int,
    data: CRMClienteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_ROLES)),
):
    c = db.query(CRMCliente).filter(CRMCliente.id == cliente_id).first()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    if current_user.rol == "asesor" and c.asesor_id != current_user.id:
        raise HTTPException(403, "Acceso denegado")

    update_data = data.model_dump(exclude_unset=True)
    asesor_cambio = "asesor_id" in update_data and update_data["asesor_id"] != c.asesor_id

    for field, value in update_data.items():
        setattr(c, field, value)
    db.commit()
    db.refresh(c)

    if asesor_cambio:
        nuevo_nombre = None
        if c.asesor_id:
            a = db.query(User).filter(User.id == c.asesor_id).first()
            nuevo_nombre = a.nombre if a else None
        from app.services.vendedor_sync import propagar_vendedor_por_nit
        propagar_vendedor_por_nit(db, c.nit, nuevo_nombre)

    return _enrich(c)
