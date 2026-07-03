from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.background import BackgroundScheduler
import logging, os

logging.basicConfig(level=logging.INFO)

# Cargar .env
try:
    _env = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(_env):
        for _l in open(_env, encoding="utf-8"):
            _l = _l.strip()
            if _l and not _l.startswith("#") and "=" in _l:
                _k, _v = _l.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
except Exception:
    pass

def _auto_sync():
    try:
        from app.services.alegra_sync import run_sync, get_status
        if not get_status()["credentials_ok"]:
            return
        logging.getLogger("alegra_sync").info("Auto-sync iniciando...")
        run_sync()
    except Exception as e:
        logging.getLogger("alegra_sync").error(f"Auto-sync error: {e}")

_scheduler = BackgroundScheduler(timezone="America/Bogota")
_scheduler.add_job(_auto_sync, "interval", hours=4, id="alegra_sync", next_run_time=None)

@asynccontextmanager
async def lifespan(app):
    _scheduler.start()
    logging.info("Scheduler: sync Alegra cada 4h")
    yield
    _scheduler.shutdown(wait=False)

from app.database import Base, engine
import app.models  # ensure all models are registered
from app.routers import auth, tables, menu, orders, inventory, payments, reports, expenses, daily_menu, menu_ciclo, cash_count, domiciliarios, clientes, credito, printer, public, trazabilidad, produccion, otros
from app.routers import crm_clientes, crm_visitas, crm_calendario, crm_pedidos, crm_cuentas, crm_tareas, crm_gerencia, crm_cartera, crm_alegra, crm_precios

Base.metadata.create_all(bind=engine)

# ── Migraciones manuales para columnas nuevas en SQLite ──────────────────────
from sqlalchemy import text
with engine.connect() as _conn:
    for _sql in [
        # Tabla de trazabilidad de estados de órdenes
        "CREATE TABLE IF NOT EXISTS order_estado_logs (id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(id), tipo_orden VARCHAR(15), estado_de VARCHAR(20), estado_a VARCHAR(20) NOT NULL, usuario_id INTEGER REFERENCES users(id), usuario_nombre VARCHAR(100), created_at DATETIME DEFAULT (datetime('now')))",
        "CREATE INDEX IF NOT EXISTS ix_order_estado_logs_order_id ON order_estado_logs(order_id)",
        "ALTER TABLE recipes ADD COLUMN unidad VARCHAR(20)",
        "ALTER TABLE daily_menus ADD COLUMN precio REAL DEFAULT 0",
        "ALTER TABLE menu_items ADD COLUMN tipo_plato VARCHAR(20)",
        "ALTER TABLE orders ADD COLUMN domiciliario_id INTEGER REFERENCES domiciliarios(id)",
        "ALTER TABLE orders ADD COLUMN valor_domicilio REAL DEFAULT 0",
        "ALTER TABLE expenses ADD COLUMN metodo_pago VARCHAR(20) DEFAULT 'efectivo'",
        "ALTER TABLE expenses ADD COLUMN caja_id INTEGER REFERENCES cash_registers(id)",
        "ALTER TABLE orders ADD COLUMN metodo_pago VARCHAR(30)",
        "ALTER TABLE orders ADD COLUMN fuente VARCHAR(10) DEFAULT 'pos'",
        "ALTER TABLE daily_menus ADD COLUMN precio_sopa REAL DEFAULT 8000",
        "ALTER TABLE daily_menus ADD COLUMN precio_proteina REAL DEFAULT 10000",
        "ALTER TABLE menu_ciclos ADD COLUMN especial_id INTEGER REFERENCES menu_items(id)",
        "ALTER TABLE orders ADD COLUMN stock_descontado INTEGER DEFAULT 0",
        "ALTER TABLE crm_clientes ADD COLUMN datha_customer_id INTEGER",
        "ALTER TABLE order_items ADD COLUMN es_adicional INTEGER DEFAULT 0",
        "CREATE TABLE IF NOT EXISTS lista_precio_productos (id INTEGER PRIMARY KEY, codigo VARCHAR(60), descripcion VARCHAR(400) NOT NULL, precio_unitario NUMERIC(18,2) NOT NULL, unidad VARCHAR(30) DEFAULT 'UND', categoria VARCHAR(100), activo INTEGER DEFAULT 1, updated_at DATETIME)",
        "CREATE INDEX IF NOT EXISTS ix_lista_precio_productos_codigo ON lista_precio_productos(codigo)",
        "CREATE INDEX IF NOT EXISTS ix_lista_precio_productos_categoria ON lista_precio_productos(categoria)",
        "CREATE TABLE IF NOT EXISTS cotizaciones (id INTEGER PRIMARY KEY, consecutivo VARCHAR(25) UNIQUE NOT NULL, asesor_id INTEGER NOT NULL REFERENCES users(id), cliente_nombre VARCHAR(200), cliente_nit VARCHAR(30), cliente_email VARCHAR(200), cliente_telefono VARCHAR(30), cliente_ciudad VARCHAR(100), notas TEXT, subtotal NUMERIC(18,2) DEFAULT 0, iva_pct NUMERIC(5,2) DEFAULT 0, iva NUMERIC(18,2) DEFAULT 0, total NUMERIC(18,2) DEFAULT 0, estado VARCHAR(20) DEFAULT 'borrador', created_at DATETIME DEFAULT (datetime('now')))",
        "CREATE INDEX IF NOT EXISTS ix_cotizaciones_consecutivo ON cotizaciones(consecutivo)",
        "CREATE TABLE IF NOT EXISTS cotizacion_items (id INTEGER PRIMARY KEY, cotizacion_id INTEGER NOT NULL REFERENCES cotizaciones(id) ON DELETE CASCADE, codigo VARCHAR(60), descripcion VARCHAR(400), unidad VARCHAR(30) DEFAULT 'UND', cantidad NUMERIC(10,2) DEFAULT 1, precio_unitario NUMERIC(18,2) DEFAULT 0, total NUMERIC(18,2) DEFAULT 0)",
        "ALTER TABLE lista_precio_productos ADD COLUMN precio_2 NUMERIC(18,2)",
        "ALTER TABLE lista_precio_productos ADD COLUMN precio_3 NUMERIC(18,2)",
        "CREATE TABLE IF NOT EXISTS lista_precio_config (id INTEGER PRIMARY KEY, label_1 VARCHAR(80), label_2 VARCHAR(80), label_3 VARCHAR(80), updated_at DATETIME)",
    ]:
        try:
            _conn.execute(text(_sql))
            _conn.commit()
        except Exception:
            pass  # columna ya existe

app = FastAPI(title="Sistema Administrativo API", version="1.0.0", lifespan=lifespan)

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
app.include_router(daily_menu.router)
app.include_router(menu_ciclo.router)
app.include_router(orders.admin_router)
app.include_router(orders.import_router)
app.include_router(cash_count.router)
app.include_router(domiciliarios.router)
app.include_router(clientes.router)
app.include_router(credito.router)
app.include_router(printer.router)
app.include_router(public.router)
app.include_router(trazabilidad.router)
app.include_router(produccion.router)
app.include_router(otros.router)
app.include_router(crm_clientes.router)
app.include_router(crm_visitas.router)
app.include_router(crm_calendario.router)
app.include_router(crm_pedidos.router)
app.include_router(crm_cuentas.router)
app.include_router(crm_tareas.router)
app.include_router(crm_gerencia.router)
app.include_router(crm_cartera.router)
app.include_router(crm_alegra.router)
app.include_router(crm_precios.router)


@app.get("/")
def root():
    return {"message": "Sistema Administrativo - API v1.0"}


@app.on_event("startup")
def seed_admin():
    from app.database import SessionLocal
    from app.models.user import User
    from app.auth.security import hash_password
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "admin").first():
            admin = User(
                nombre="Administrador",
                username="admin",
                password_hash=hash_password("admin123"),
                rol="admin"
            )
            db.add(admin)
            db.commit()
            print("Usuario admin creado: admin / admin123")
    finally:
        db.close()
