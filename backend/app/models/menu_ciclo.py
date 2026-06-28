from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class MenuCiclo(Base):
    __tablename__ = "menu_ciclos"

    id          = Column(Integer, primary_key=True, index=True)
    ciclo       = Column(Integer, nullable=False)       # 1-4
    dia_semana  = Column(Integer, nullable=False)       # 1=Lunes … 7=Domingo
    sopa_id     = Column(Integer, ForeignKey("menu_items.id"), nullable=True)
    proteina_id = Column(Integer, ForeignKey("menu_items.id"), nullable=True)
    ensalada_id = Column(Integer, ForeignKey("menu_items.id"), nullable=True)
    especial_id = Column(Integer, ForeignKey("menu_items.id"), nullable=True)
    contorno    = Column(String(300), nullable=True)    # texto libre separado por comas

    sopa     = relationship("MenuItem", foreign_keys=[sopa_id])
    proteina = relationship("MenuItem", foreign_keys=[proteina_id])
    ensalada = relationship("MenuItem", foreign_keys=[ensalada_id])
    especial = relationship("MenuItem", foreign_keys=[especial_id])

    __table_args__ = (UniqueConstraint("ciclo", "dia_semana", name="uq_ciclo_dia"),)


class MenuCicloConfig(Base):
    __tablename__ = "menu_ciclo_config"

    id            = Column(Integer, primary_key=True, index=True)
    ciclo_activo  = Column(Integer, default=1, nullable=False)
