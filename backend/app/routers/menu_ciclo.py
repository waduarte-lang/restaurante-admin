from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import date

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.models.menu_ciclo import MenuCiclo, MenuCicloConfig
from app.schemas.menu_ciclo import (
    MenuCicloOut, MenuCicloBulkIn,
    MenuCicloConfigOut, MenuCicloConfigIn,
)

router = APIRouter(prefix="/api/menu-ciclo", tags=["menu-ciclo"])

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _out(row: MenuCiclo) -> MenuCicloOut:
    return MenuCicloOut(
        id=row.id,
        ciclo=row.ciclo,
        dia_semana=row.dia_semana,
        sopa_id=row.sopa_id,
        proteina_id=row.proteina_id,
        ensalada_id=row.ensalada_id,
        especial_id=row.especial_id,
        contorno=row.contorno,
        sopa_nombre=row.sopa.nombre if row.sopa else None,
        proteina_nombre=row.proteina.nombre if row.proteina else None,
        ensalada_nombre=row.ensalada.nombre if row.ensalada else None,
        especial_nombre=row.especial.nombre if row.especial else None,
    )


def _ensure_config(db: Session) -> MenuCicloConfig:
    cfg = db.query(MenuCicloConfig).first()
    if not cfg:
        cfg = MenuCicloConfig(ciclo_activo=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


# ── Ciclo config ────────────────────────────────────────────────────────────

@router.get("/config", response_model=MenuCicloConfigOut)
def get_config(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _ensure_config(db)


@router.put("/config", response_model=MenuCicloConfigOut)
def set_config(body: MenuCicloConfigIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if body.ciclo_activo not in (1, 2, 3, 4):
        raise HTTPException(400, "ciclo_activo debe ser 1-4")
    cfg = _ensure_config(db)
    cfg.ciclo_activo = body.ciclo_activo
    db.commit()
    db.refresh(cfg)
    return cfg


# ── Today suggestion ─────────────────────────────────────────────────────────

@router.get("/today-suggestion", response_model=MenuCicloOut)
def today_suggestion(db: Session = Depends(get_db), _=Depends(get_current_user)):
    cfg = _ensure_config(db)
    # date.isoweekday(): 1=Mon … 7=Sun
    dia = date.today().isoweekday()
    row = db.query(MenuCiclo).filter(
        MenuCiclo.ciclo == cfg.ciclo_activo,
        MenuCiclo.dia_semana == dia,
    ).first()
    if not row:
        raise HTTPException(404, f"No hay menú configurado para ciclo {cfg.ciclo_activo}, día {DIAS[dia-1]}")
    return _out(row)


# ── All records ───────────────────────────────────────────────────────────────

@router.get("/", response_model=List[MenuCicloOut])
def list_all(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = db.query(MenuCiclo).order_by(MenuCiclo.ciclo, MenuCiclo.dia_semana).all()
    return [_out(r) for r in rows]


# ── By ciclo ──────────────────────────────────────────────────────────────────

@router.get("/{ciclo}", response_model=List[MenuCicloOut])
def get_ciclo(ciclo: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if ciclo not in (1, 2, 3, 4):
        raise HTTPException(400, "ciclo debe ser 1-4")
    rows = db.query(MenuCiclo).filter(MenuCiclo.ciclo == ciclo).order_by(MenuCiclo.dia_semana).all()
    return [_out(r) for r in rows]


# ── Bulk save ─────────────────────────────────────────────────────────────────

@router.post("/bulk", response_model=List[MenuCicloOut])
def save_bulk(body: MenuCicloBulkIn, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if body.ciclo not in (1, 2, 3, 4):
        raise HTTPException(400, "ciclo debe ser 1-4")

    results = []
    for d in body.dias:
        if d.dia_semana not in range(1, 8):
            raise HTTPException(400, f"dia_semana inválido: {d.dia_semana}")

        row = db.query(MenuCiclo).filter(
            MenuCiclo.ciclo == body.ciclo,
            MenuCiclo.dia_semana == d.dia_semana,
        ).first()

        if row:
            row.sopa_id = d.sopa_id
            row.proteina_id = d.proteina_id
            row.ensalada_id = d.ensalada_id
            row.especial_id = d.especial_id
            row.contorno = d.contorno
        else:
            row = MenuCiclo(
                ciclo=body.ciclo,
                dia_semana=d.dia_semana,
                sopa_id=d.sopa_id,
                proteina_id=d.proteina_id,
                ensalada_id=d.ensalada_id,
                especial_id=d.especial_id,
                contorno=d.contorno,
            )
            db.add(row)

        db.flush()
        db.refresh(row)
        results.append(_out(row))

    db.commit()
    return results
