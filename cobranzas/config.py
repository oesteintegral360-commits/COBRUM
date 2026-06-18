"""
Configuración del proyecto.

La idea clave: la base de datos vive detrás de una sola línea (DATABASE_URL). Hoy es
SQLite (un archivo local, no hay que instalar nada). El día que comercialicemos,
cambiamos esta línea por una de PostgreSQL en la nube y NO se toca nada más del código.
"""

import os
from pathlib import Path

# Carpeta raíz del proyecto (la que contiene este paquete).
RAIZ = Path(__file__).resolve().parent.parent

# Carpeta donde guardamos datos locales (la base y los ejemplos).
CARPETA_DATOS = RAIZ / "datos"


def _normalizar_db_url(url: str) -> str:
    """La nube suele dar 'postgres://'; SQLAlchemy necesita 'postgresql://'."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


# Dónde vive la base de datos.
#   - En tu compu (local): SQLite, un archivo. No hay que configurar nada.
#   - En la nube: se toma de la variable de entorno DATABASE_URL (PostgreSQL) que
#     configura el servidor (Render). NO se reescribe nada del código.
_SQLITE_LOCAL = f"sqlite:///{CARPETA_DATOS / 'cobranzas.db'}"
DATABASE_URL = _normalizar_db_url(os.environ.get("DATABASE_URL", _SQLITE_LOCAL))

# Dirección base con la que se arman los links de pago que se mandan al cliente.
#   - Local: http://localhost:8011
#   - Nube: Render expone la URL pública sola en RENDER_EXTERNAL_URL.
BASE_URL = (os.environ.get("BASE_URL")
            or os.environ.get("RENDER_EXTERNAL_URL")
            or "http://localhost:8011").rstrip("/")
