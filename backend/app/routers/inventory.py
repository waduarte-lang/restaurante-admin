from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models.inventory import Ingredient, Recipe, StockMovement
from app.models.menu import MenuItem
from app.schemas.inventory import (IngredientCreate, IngredientUpdate, IngredientOut,
                                    StockMovementCreate, StockMovementOut,
                                    RecipeCreate, RecipeOut)
from app.auth.dependencies import get_current_user, admin_only
from app.models.user import User

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("/ingredients", response_model=List[IngredientOut])
def list_ingredients(db: Session = Depends(get_db), _=Depends(get_current_user)):
    ingredients = db.query(Ingredient).all()
    result = []
    for ing in ingredients:
        d = {c.name: getattr(ing, c.name) for c in ing.__table__.columns}
        d["bajo_stock"] = ing.stock_actual <= ing.stock_minimo
        result.append(d)
    return result


@router.post("/ingredients", response_model=IngredientOut)
def create_ingredient(data: IngredientCreate, db: Session = Depends(get_db), _=Depends(admin_only)):
    ing = Ingredient(**data.model_dump())
    db.add(ing)
    db.commit()
    db.refresh(ing)
    d = {c.name: getattr(ing, c.name) for c in ing.__table__.columns}
    d["bajo_stock"] = ing.stock_actual <= ing.stock_minimo
    return d


@router.put("/ingredients/{ing_id}", response_model=IngredientOut)
def update_ingredient(ing_id: int, data: IngredientUpdate, db: Session = Depends(get_db), _=Depends(admin_only)):
    ing = db.query(Ingredient).filter(Ingredient.id == ing_id).first()
    if not ing:
        raise HTTPException(status_code=404, detail="Ingrediente no encontrado")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(ing, field, value)
    db.commit()
    db.refresh(ing)
    d = {c.name: getattr(ing, c.name) for c in ing.__table__.columns}
    d["bajo_stock"] = ing.stock_actual <= ing.stock_minimo
    return d


@router.post("/movements", response_model=StockMovementOut)
def register_movement(data: StockMovementCreate, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    ing = db.query(Ingredient).filter(Ingredient.id == data.ingredient_id).first()
    if not ing:
        raise HTTPException(status_code=404, detail="Ingrediente no encontrado")
    if data.tipo == "entrada":
        ing.stock_actual += data.cantidad
    elif data.tipo == "salida":
        if ing.stock_actual < data.cantidad:
            raise HTTPException(status_code=400, detail="Stock insuficiente")
        ing.stock_actual -= data.cantidad
    mov = StockMovement(ingredient_id=data.ingredient_id, tipo=data.tipo,
                        cantidad=data.cantidad, motivo=data.motivo, usuario_id=current_user.id)
    db.add(mov)
    db.commit()
    db.refresh(mov)
    return mov


@router.get("/movements", response_model=List[StockMovementOut])
def list_movements(ingredient_id: int = None, db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(StockMovement)
    if ingredient_id:
        q = q.filter(StockMovement.ingredient_id == ingredient_id)
    return q.order_by(StockMovement.created_at.desc()).limit(100).all()


@router.get("/recipes/{item_id}", response_model=List[RecipeOut])
def get_recipes(item_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    recipes = db.query(Recipe).filter(Recipe.item_id == item_id).all()
    result = []
    for r in recipes:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        d["ingrediente_nombre"] = r.ingrediente.nombre if r.ingrediente else None
        d["unidad"] = r.ingrediente.unidad if r.ingrediente else None
        result.append(d)
    return result


@router.post("/recipes", response_model=RecipeOut)
def create_recipe(data: RecipeCreate, db: Session = Depends(get_db), _=Depends(admin_only)):
    recipe = Recipe(**data.model_dump())
    db.add(recipe)
    db.commit()
    db.refresh(recipe)
    d = {c.name: getattr(recipe, c.name) for c in recipe.__table__.columns}
    d["ingrediente_nombre"] = recipe.ingrediente.nombre if recipe.ingrediente else None
    d["unidad"] = recipe.ingrediente.unidad if recipe.ingrediente else None
    return d


@router.delete("/recipes/{recipe_id}")
def delete_recipe(recipe_id: int, db: Session = Depends(get_db), _=Depends(admin_only)):
    r = db.query(Recipe).filter(Recipe.id == recipe_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Receta no encontrada")
    db.delete(r)
    db.commit()
    return {"ok": True}
