from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.menu import MenuCategory, MenuItem
from app.schemas.menu import CategoryCreate, CategoryOut, MenuItemCreate, MenuItemUpdate, MenuItemOut
from app.auth.dependencies import get_current_user, admin_only

router = APIRouter(prefix="/api/menu", tags=["menu"])


@router.get("/categories", response_model=List[CategoryOut])
def list_categories(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(MenuCategory).order_by(MenuCategory.orden).all()


@router.post("/categories", response_model=CategoryOut)
def create_category(data: CategoryCreate, db: Session = Depends(get_db), _=Depends(admin_only)):
    cat = MenuCategory(**data.model_dump())
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db), _=Depends(admin_only)):
    cat = db.query(MenuCategory).filter(MenuCategory.id == cat_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Categoría no encontrada")
    db.delete(cat)
    db.commit()
    return {"ok": True}


@router.get("/items", response_model=List[MenuItemOut])
def list_items(activo: bool = True, db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(MenuItem)
    if activo:
        q = q.filter(MenuItem.activo == True)
    return q.all()


@router.post("/items", response_model=MenuItemOut)
def create_item(data: MenuItemCreate, db: Session = Depends(get_db), _=Depends(admin_only)):
    item = MenuItem(**data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.put("/items/{item_id}", response_model=MenuItemOut)
def update_item(item_id: int, data: MenuItemUpdate, db: Session = Depends(get_db), _=Depends(admin_only)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Ítem no encontrado")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db), _=Depends(admin_only)):
    item = db.query(MenuItem).filter(MenuItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Ítem no encontrado")
    item.activo = False
    db.commit()
    return {"ok": True}
