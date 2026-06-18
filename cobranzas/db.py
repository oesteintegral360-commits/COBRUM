"""
Conexión a la base de datos (SQLAlchemy).

Este archivo crea el "engine" (la conexión) y la fábrica de sesiones. El resto del
código pide una sesión acá y no se preocupa por qué motor hay debajo.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from cobranzas.config import DATABASE_URL, CARPETA_DATOS


# Nos aseguramos de que exista la carpeta de datos (donde va el archivo .db).
CARPETA_DATOS.mkdir(parents=True, exist_ok=True)


# El "engine" es la conexión al motor. check_same_thread=False es lo recomendado
# para usar SQLite desde un servidor web (FastAPI).
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


# Fábrica de sesiones: cada operación con la base abre una sesión desde acá.
Sesion = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Clase base de la que heredan todos los modelos (las tablas)."""


def crear_tablas() -> None:
    """Crea todas las tablas en la base si todavía no existen."""
    # Importamos los modelos acá adentro para que queden registrados en Base
    # antes de crear las tablas (evita problemas de orden de importación).
    from cobranzas import modelos  # noqa: F401

    Base.metadata.create_all(engine)
