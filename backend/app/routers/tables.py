from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.table import Table
from app.schemas.table import TableCreate, TableUpdate, TableOut
from app.auth.dependencies import get_current_user, admin_only

router = APIRouter(prefix="/api/tables", tags=["tables"])


@router.get("", response_model=List[TableOut])
def list_tables(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Table).order_by(Table.numero).all()


@router.post("", response_model=TableOut)
def create_table(data: TableCreate, db: Session = Depends(get_db), _=Depends(admin_only)):
    if db.query(Table).filter(Table.numero == data.numero).first():
        raise HTTPException(status_code=400, detail="Número de mesa ya existe")
    table = Table(**data.model_dump())
    db.add(table)
    db.commit()
    db.refresh(table)
    return table


@router.put("/{table_id}", response_model=TableOut)
def update_table(table_id: int, data: TableUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    table = db.query(Table).filter(Table.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Mesa no encontrada")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(table, field, value)
    db.commit()
    db.refresh(table)
    return table


@router.delete("/{table_id}")
def delete_table(table_id: int, db: Session = Depends(get_db), _=Depends(admin_only)):
    table = db.query(Table).filter(Table.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Mesa no encontrada")
    db.delete(table)
    db.commit()
    return {"ok": True}
