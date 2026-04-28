from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date
from app.database import get_db
from app.models.expense import Expense
from app.schemas.expense import ExpenseCreate, ExpenseUpdate, ExpenseOut
from app.auth.dependencies import get_current_user, require_roles
from app.models.user import User

router = APIRouter(prefix="/api/expenses", tags=["expenses"])


@router.get("", response_model=List[ExpenseOut])
def list_expenses(
    fecha_inicio: Optional[date] = Query(default=None),
    fecha_fin: Optional[date] = Query(default=None),
    categoria: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    _=Depends(require_roles("admin", "cajero"))
):
    q = db.query(Expense)
    if fecha_inicio:
        q = q.filter(Expense.fecha >= fecha_inicio)
    if fecha_fin:
        q = q.filter(Expense.fecha <= fecha_fin)
    if categoria:
        q = q.filter(Expense.categoria == categoria)
    return q.order_by(Expense.fecha.desc()).all()


@router.post("", response_model=ExpenseOut)
def create_expense(data: ExpenseCreate, db: Session = Depends(get_db),
                    current_user: User = Depends(require_roles("admin", "cajero"))):
    expense = Expense(**data.model_dump(), usuario_id=current_user.id)
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


@router.put("/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: int, data: ExpenseUpdate, db: Session = Depends(get_db),
                    _=Depends(require_roles("admin"))):
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(expense, field, value)
    db.commit()
    db.refresh(expense)
    return expense


@router.delete("/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db), _=Depends(require_roles("admin"))):
    expense = db.query(Expense).filter(Expense.id == expense_id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Gasto no encontrado")
    db.delete(expense)
    db.commit()
    return {"ok": True}
