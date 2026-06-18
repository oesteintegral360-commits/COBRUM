"""
La web de COBRUM (Fase 1): subir la foto (Excel) y ver la lista.

Es a propósito mínima y "acción-first": una sola acción importante por pantalla.
  - GET  /         -> pantalla de inicio con el botón grande "Subir foto".
  - POST /subir    -> recibe el Excel, lo importa y redirige a la lista.
  - GET  /clientes -> la lista de clientes con sus facturas, vencidos y tramos.
"""

from datetime import date
from pathlib import Path
import shutil

from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from cobranzas.db import Sesion, crear_tablas
from cobranzas.modelos import Cliente, ImportSnapshot
from cobranzas.importador import importar_foto
from cobranzas import motor

AQUI = Path(__file__).resolve().parent
SUBIDOS = AQUI / "subidos"
SUBIDOS.mkdir(exist_ok=True)

app = FastAPI(title="COBRUM")
app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")
plantillas = Jinja2Templates(directory=AQUI / "templates")

# Creamos las tablas al arrancar (si no existen).
crear_tablas()

# Guardamos el último resultado de import para mostrar el resumen tras subir.
_ultimo_resultado = {"datos": None}


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    """Pantalla de inicio: el botón grande para subir la foto."""
    return plantillas.TemplateResponse("inicio.html", {"request": request})


@app.post("/subir")
async def subir(archivo: UploadFile = File(...)):
    """Recibe el Excel, lo guarda, lo importa y redirige a la lista."""
    destino = SUBIDOS / archivo.filename
    with destino.open("wb") as f:
        shutil.copyfileobj(archivo.file, f)

    sesion = Sesion()
    try:
        resultado = importar_foto(sesion, str(destino), nombre_archivo=archivo.filename)
    finally:
        sesion.close()

    _ultimo_resultado["datos"] = resultado
    return RedirectResponse(url="/clientes", status_code=303)


@app.get("/clientes", response_class=HTMLResponse)
def lista_clientes(request: Request):
    """La lista de clientes con sus facturas, vencidos, días de atraso y tramo."""
    hoy = date.today()
    sesion = Sesion()
    try:
        clientes = sesion.query(Cliente).all()

        # Armamos una estructura simple y ya calculada para la plantilla.
        tarjetas = []
        for c in clientes:
            facturas = list(c.facturas)
            facturas_info = []
            for f in facturas:
                dias = motor.dias_atraso(f, hoy)
                facturas_info.append({
                    "numero": f.numero_factura,
                    "saldo": float(f.saldo_pendiente),
                    "vencimiento": f.fecha_vencimiento,
                    "estado": f.estado,
                    "vencida": motor.esta_vencida(f, hoy),
                    "dias_atraso": dias,
                    "tramo": motor.tramo_atraso(dias),
                })
            # Mostramos primero las más atrasadas.
            facturas_info.sort(key=lambda x: x["dias_atraso"], reverse=True)

            total = motor.total_por_cliente(facturas)
            # Solo listamos clientes que tengan algo pendiente.
            if total <= 0:
                continue
            tarjetas.append({
                "cuit": c.cuit,
                "nombre": c.nombre or "(sin nombre)",
                "vendedor": c.vendedor_asignado or "",
                "falta_telefono": c.falta_telefono,
                "cuit_sospechoso": c.cuit_sospechoso,
                "total": float(total),
                "facturas": facturas_info,
            })

        # Ordenamos los clientes por deuda total (de mayor a menor).
        tarjetas.sort(key=lambda t: t["total"], reverse=True)

        snapshot = sesion.query(ImportSnapshot).order_by(ImportSnapshot.id.desc()).first()
    finally:
        sesion.close()

    return plantillas.TemplateResponse("lista.html", {
        "request": request,
        "tarjetas": tarjetas,
        "resultado": _ultimo_resultado["datos"],
        "snapshot": snapshot,
        "hoy": hoy,
    })
