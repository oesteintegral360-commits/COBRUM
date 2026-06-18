"""
Genera los Excel de ejemplo para demostrar el motor (datos ficticios).

Correlo una sola vez con:  python generar_ejemplos.py
Crea:
  - datos/ejemplos/foto_1.xlsx : una distribuidora con varios clientes y facturas.
  - datos/ejemplos/foto_2.xlsx : igual que la 1, pero con 1 factura NUEVA y 1 que
    DESAPARECE (para demostrar que la foto reemplaza y la desaparecida queda pagada).

A propósito incluimos un cliente con CUIT de dígito verificador inválido, para mostrar
el aviso que no bloquea la carga.
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

CARPETA = Path(__file__).resolve().parent / "datos" / "ejemplos"
CARPETA.mkdir(parents=True, exist_ok=True)

# Usamos una fecha base fija para que el ejemplo sea estable y reproducible.
HOY = date(2026, 6, 18)


def _digito_verificador(base10: str) -> int:
    """Calcula el dígito verificador correcto para los primeros 10 dígitos del CUIT."""
    mult = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    suma = sum(int(base10[i]) * mult[i] for i in range(10))
    resto = suma % 11
    ver = 11 - resto
    if ver == 11:
        return 0
    if ver == 10:
        return 1  # caso raro: forzamos algo; para el ejemplo evitamos estas bases.
    return ver


def cuit_valido(base10: str) -> str:
    """Devuelve un CUIT de 11 dígitos válido a partir de 10 dígitos."""
    return base10 + str(_digito_verificador(base10))


def cuit_invalido(base10: str) -> str:
    """Devuelve un CUIT cuyo último dígito NO cierra (para demostrar el aviso)."""
    correcto = _digito_verificador(base10)
    roto = (correcto + 1) % 10
    return base10 + str(roto)


# CUITs (con guiones, para demostrar que la normalización los une igual).
CUIT_KIOSCO = cuit_valido("2030111222")     # Kiosco La Esquina
CUIT_ALMACEN = cuit_valido("2733444555")    # Almacén Doña Rosa
CUIT_FERRE = cuit_valido("3055666777")      # Ferretería El Tornillo
CUIT_PANADERIA = cuit_invalido("2088999111")  # Panadería La Espiga (CUIT roto a propósito)


def con_guiones(cuit: str) -> str:
    """Le pone el formato 30-11122233-4 para que el Excel se vea realista."""
    return f"{cuit[:2]}-{cuit[2:10]}-{cuit[10]}"


# --- FOTO 1 ---------------------------------------------------------------------
filas_1 = [
    # CUIT, Razón social, Teléfono, Vendedor, Número factura, Saldo, Vencimiento
    [con_guiones(CUIT_KIOSCO), "Kiosco La Esquina", "+54 9 11 5555-1001", "Juan Pérez",
     "A-0001", "15.000,00", HOY - timedelta(days=45)],
    [con_guiones(CUIT_KIOSCO), "Kiosco La Esquina", "+54 9 11 5555-1001", "Juan Pérez",
     "A-0002", "8.500,50", HOY - timedelta(days=10)],
    [con_guiones(CUIT_ALMACEN), "Almacén Doña Rosa", "+54 9 11 5555-2002", "María Gómez",
     "A-0003", "32.000,00", HOY - timedelta(days=70)],
    [con_guiones(CUIT_FERRE), "Ferretería El Tornillo", "", "Juan Pérez",
     "A-0004", "5.200,00", HOY + timedelta(days=15)],  # todavía no vencida
    [con_guiones(CUIT_PANADERIA), "Panadería La Espiga", "+54 9 11 5555-4004", "María Gómez",
     "A-0005", "12.750,00", HOY - timedelta(days=3)],
]

columnas = ["CUIT", "Razón social", "Teléfono", "Vendedor", "Número factura", "Saldo", "Vencimiento"]
df1 = pd.DataFrame(filas_1, columns=columnas)
df1.to_excel(CARPETA / "foto_1.xlsx", index=False)


# --- FOTO 2 ---------------------------------------------------------------------
# Igual que la foto 1 pero:
#   - DESAPARECE la factura A-0001 (se asume pagada).
#   - APARECE una factura NUEVA A-0006.
#   - A-0003 cambia de saldo (pago parcial).
filas_2 = [
    [con_guiones(CUIT_KIOSCO), "Kiosco La Esquina", "+54 9 11 5555-1001", "Juan Pérez",
     "A-0002", "8.500,50", HOY - timedelta(days=12)],
    [con_guiones(CUIT_ALMACEN), "Almacén Doña Rosa", "+54 9 11 5555-2002", "María Gómez",
     "A-0003", "20.000,00", HOY - timedelta(days=72)],  # pagó una parte
    [con_guiones(CUIT_FERRE), "Ferretería El Tornillo", "", "Juan Pérez",
     "A-0004", "5.200,00", HOY + timedelta(days=13)],
    [con_guiones(CUIT_PANADERIA), "Panadería La Espiga", "+54 9 11 5555-4004", "María Gómez",
     "A-0005", "12.750,00", HOY - timedelta(days=5)],
    [con_guiones(CUIT_ALMACEN), "Almacén Doña Rosa", "+54 9 11 5555-2002", "María Gómez",
     "A-0006", "18.300,00", HOY - timedelta(days=1)],  # factura NUEVA
]

df2 = pd.DataFrame(filas_2, columns=columnas)
df2.to_excel(CARPETA / "foto_2.xlsx", index=False)

print("Listo. Generados:")
print(" -", CARPETA / "foto_1.xlsx")
print(" -", CARPETA / "foto_2.xlsx")
