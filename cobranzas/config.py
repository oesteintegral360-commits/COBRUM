"""
Configuración del proyecto.

La idea clave: la base de datos vive detrás de una sola línea (DATABASE_URL). Hoy es
SQLite (un archivo local, no hay que instalar nada). El día que comercialicemos,
cambiamos esta línea por una de PostgreSQL en la nube y NO se toca nada más del código.
"""

from pathlib import Path

# Carpeta raíz del proyecto (la que contiene este paquete).
RAIZ = Path(__file__).resolve().parent.parent

# Carpeta donde guardamos datos locales (la base y los ejemplos).
CARPETA_DATOS = RAIZ / "datos"

# Dónde vive la base de datos.
#   - Hoy (local):  sqlite:///.../datos/cobranzas.db
#   - Mañana (nube): postgresql://usuario:clave@servidor/cobranzas
# Para cambiar de motor, se cambia SOLO esta variable.
DATABASE_URL = f"sqlite:///{CARPETA_DATOS / 'cobranzas.db'}"
