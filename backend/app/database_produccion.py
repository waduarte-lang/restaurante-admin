"""Conexión a la base de datos de producción (servidor externo)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

PRODUCCION_DB_URL = (
    "postgresql://comercial:zXpAkK1BUlhuZhjHpZlslw"
    "@144.217.183.135:5435/DATHA"
)

prod_engine = create_engine(
    PRODUCCION_DB_URL,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=5,
    pool_timeout=8,
    connect_args={"connect_timeout": 5},
)

ProdSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=prod_engine)


def get_prod_db():
    db = ProdSessionLocal()
    try:
        yield db
    finally:
        db.close()
