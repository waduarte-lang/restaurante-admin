from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine
import app.models  # ensure all models are registered
from app.routers import auth, tables, menu, orders, inventory, payments, reports, expenses

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Sistema Administrativo Restaurante", version="1.0.0")

import os
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tables.router)
app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(inventory.router)
app.include_router(payments.router)
app.include_router(reports.router)
app.include_router(expenses.router)


@app.get("/")
def root():
    return {"message": "Sistema Administrativo Restaurante - API v1.0"}


@app.on_event("startup")
def seed_admin():
    from app.database import SessionLocal
    from app.models.user import User
    from app.auth.security import hash_password
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "admin@restaurante.com").first():
            admin = User(
                nombre="Administrador",
                email="admin@restaurante.com",
                password_hash=hash_password("admin123"),
                rol="admin"
            )
            db.add(admin)
            db.commit()
            print("Usuario admin creado: admin@restaurante.com / admin123")
    finally:
        db.close()
