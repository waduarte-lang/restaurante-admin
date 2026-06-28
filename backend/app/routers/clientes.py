from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import List

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models.cliente import Cliente
from app.schemas.cliente import ClienteIn, ClienteOut

router = APIRouter(prefix="/api/clientes", tags=["clientes"])


@router.get("/", response_model=List[ClienteOut])
def search_clientes(
    q: str = Query(default=""),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = db.query(Cliente)
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Cliente.nombre.ilike(term),
                Cliente.telefono.ilike(term),
            )
        )
    return query.order_by(Cliente.nombre).limit(20).all()


@router.post("/", response_model=ClienteOut)
def create_cliente(
    body: ClienteIn,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    c = Cliente(**body.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.put("/{cliente_id}", response_model=ClienteOut)
def update_cliente(
    cliente_id: int,
    body: ClienteIn,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    c = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{cliente_id}")
def delete_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    c = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not c:
        raise HTTPException(404, "Cliente no encontrado")
    db.delete(c)
    db.commit()
    return {"detail": "Cliente eliminado"}
