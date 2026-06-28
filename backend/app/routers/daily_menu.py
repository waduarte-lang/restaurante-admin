from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
from app.database import get_db
from app.models.daily_menu import DailyMenu, DailyMenuItem
from app.schemas.daily_menu import DailyMenuCreate, DailyMenuOut
from app.auth.dependencies import get_current_user, admin_only
from app.models.user import User

router = APIRouter(prefix="/api/daily-menu", tags=["daily-menu"])


def _build_out(menu: DailyMenu) -> dict:
    items = []
    for i in menu.items:
        nombre = None
        if i.menu_item_id and i.menu_item:
            nombre = i.menu_item.nombre
        elif i.contorno_nombre:
            nombre = i.contorno_nombre
        items.append({
            "id": i.id,
            "tipo": i.tipo,
            "menu_item_id": i.menu_item_id,
            "contorno_nombre": i.contorno_nombre,
            "nombre": nombre,
            "proteina_nombre": i.menu_item.nombre if i.tipo == "combinacion" and i.menu_item else None,
        })
    return {
        "id": menu.id,
        "fecha": menu.fecha,
        "activo": menu.activo,
        "precio": menu.precio or 0.0,
        "precio_sopa": menu.precio_sopa or 8000.0,
        "precio_proteina": menu.precio_proteina or 10000.0,
        "items": items,
    }


@router.get("/today")
def get_today(db: Session = Depends(get_db), _=Depends(get_current_user)):
    menu = db.query(DailyMenu).filter(DailyMenu.fecha == date.today(), DailyMenu.activo == True).first()
    if not menu:
        raise HTTPException(status_code=404, detail="No hay menú del día configurado")
    return _build_out(menu)


@router.get("/upcoming")
def get_upcoming(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Returns today's menu, or tomorrow's if today has none (restaurant plans ahead)."""
    from datetime import timedelta
    for delta in [0, 1]:
        d = date.today() + timedelta(days=delta)
        menu = db.query(DailyMenu).filter(DailyMenu.fecha == d, DailyMenu.activo == True).first()
        if menu:
            result = _build_out(menu)
            result["fecha_label"] = "hoy" if delta == 0 else "mañana"
            return result
    raise HTTPException(status_code=404, detail="No hay menú configurado para hoy ni mañana")


@router.get("/latest")
def get_latest(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Retorna el menú más reciente guardado (cualquier fecha), útil para pre-llenar el formulario."""
    menu = db.query(DailyMenu).order_by(DailyMenu.fecha.desc()).first()
    if not menu:
        raise HTTPException(status_code=404, detail="No hay ningún menú guardado")
    return _build_out(menu)


@router.get("/{fecha}")
def get_by_date(fecha: date, db: Session = Depends(get_db), _=Depends(get_current_user)):
    menu = db.query(DailyMenu).filter(DailyMenu.fecha == fecha).first()
    if not menu:
        raise HTTPException(status_code=404, detail="No hay menú para esa fecha")
    return _build_out(menu)


@router.post("")
def create_or_update(data: DailyMenuCreate, db: Session = Depends(get_db),
                      current_user: User = Depends(admin_only)):
    existing = db.query(DailyMenu).filter(DailyMenu.fecha == data.fecha).first()
    if existing:
        for item in existing.items:
            db.delete(item)
        db.flush()
        menu = existing
        menu.precio = data.precio
        menu.precio_sopa = data.precio_sopa
        menu.precio_proteina = data.precio_proteina
    else:
        menu = DailyMenu(
            fecha=data.fecha, precio=data.precio,
            precio_sopa=data.precio_sopa, precio_proteina=data.precio_proteina,
            creado_por=current_user.id,
        )
        db.add(menu)
        db.flush()

    for item_data in data.items:
        di = DailyMenuItem(
            daily_menu_id=menu.id,
            tipo=item_data.tipo,
            menu_item_id=item_data.menu_item_id,
            contorno_nombre=item_data.contorno_nombre,
        )
        db.add(di)

    db.commit()
    db.refresh(menu)
    return _build_out(menu)


@router.delete("/{fecha}")
def delete_menu(fecha: date, db: Session = Depends(get_db), _=Depends(admin_only)):
    menu = db.query(DailyMenu).filter(DailyMenu.fecha == fecha).first()
    if not menu:
        raise HTTPException(status_code=404, detail="No encontrado")
    db.delete(menu)
    db.commit()
    return {"ok": True}
