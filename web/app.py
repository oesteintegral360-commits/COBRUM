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

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from cobranzas.db import Sesion, crear_tablas
from cobranzas.modelos import Cliente, ImportSnapshot, Configuracion
from cobranzas.importador import importar_foto
from cobranzas import motor
from cobranzas import planes as planes_mod

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

        snap = sesion.query(ImportSnapshot).order_by(ImportSnapshot.id.desc()).first()
        # Lo pasamos como datos planos para que la plantilla no dependa de la sesión.
        snapshot = None
        if snap is not None:
            snapshot = {
                "nombre_archivo": snap.nombre_archivo,
                "cantidad_facturas": snap.cantidad_facturas,
                "total_pendiente": float(snap.total_pendiente),
            }

        # --- Aviso de límite del plan (avisar y sugerir, nunca bloquear) ---
        config = Configuracion.obtener(sesion)
        plan = planes_mod.plan_por_clave(config.plan_actual)
        cantidad_clientes = len(tarjetas)
        # Vendedores distintos en uso (entre los clientes con deuda).
        vendedores = {t["vendedor"].strip() for t in tarjetas if t["vendedor"].strip()}
        avisos_limite = planes_mod.chequear_limites(
            plan, len(vendedores), cantidad_clientes, config.vendedores_adicionales
        )
    finally:
        sesion.close()

    return plantillas.TemplateResponse("lista.html", {
        "request": request,
        "tarjetas": tarjetas,
        "resultado": _ultimo_resultado["datos"],
        "snapshot": snapshot,
        "hoy": hoy,
        "avisos_limite": avisos_limite,
        "plan_actual": plan,
    })


@app.get("/planes", response_class=HTMLResponse)
def pagina_planes(request: Request, periodo: str = "mensual"):
    """Landing de precios: las 3 tarjetas, con precio en USD y en pesos."""
    sesion = Sesion()
    try:
        config = Configuracion.obtener(sesion)
        valor_dolar = float(config.valor_dolar)
        plan_actual_clave = config.plan_actual
        dolar_configurado = config.dolar_configurado
    finally:
        sesion.close()

    anual = (periodo == "anual")
    tarjetas = []
    for p in planes_mod.PLANES:
        precio_usd = p.precio_anual_usd() if anual else p.precio_usd
        # En anual, mostramos el equivalente mensual prorrateado (precio_año / 12).
        usd_por_mes = (p.precio_anual_usd() / 12) if anual else p.precio_usd
        tarjetas.append({
            "clave": p.clave,
            "nombre": p.nombre,
            "desde": p.desde,
            "destacado": p.destacado,
            "resumen": p.resumen,
            "texto_limites": p.texto_limites,
            "beneficios": p.beneficios,
            "permite_addon": p.permite_addon,
            "usd_mes": round(usd_por_mes),
            "pesos_mes": round(usd_por_mes * valor_dolar),
            "es_actual": (p.clave == plan_actual_clave),
        })

    return plantillas.TemplateResponse("planes.html", {
        "request": request,
        "tarjetas": tarjetas,
        "anual": anual,
        "valor_dolar": valor_dolar,
        "dolar_configurado": dolar_configurado,
        "addon_usd": planes_mod.ADDON_VENDEDOR_USD,
        "meses_gratis": planes_mod.MESES_GRATIS_ANUAL,
    })


@app.post("/planes/elegir")
def elegir_plan(clave: str = Form(...)):
    """Guarda el plan elegido (se recuerda; no se vuelve a preguntar)."""
    sesion = Sesion()
    try:
        config = Configuracion.obtener(sesion)
        config.plan_actual = planes_mod.plan_por_clave(clave).clave
        sesion.commit()
    finally:
        sesion.close()
    return RedirectResponse(url="/planes", status_code=303)


@app.get("/configuracion", response_class=HTMLResponse)
def pagina_configuracion(request: Request, guardado: bool = False):
    """Pantalla donde se fija el valor del dólar (una vez; queda guardado)."""
    sesion = Sesion()
    try:
        config = Configuracion.obtener(sesion)
        datos = {
            "valor_dolar": float(config.valor_dolar),
            "dolar_configurado": config.dolar_configurado,
            "plan_actual": planes_mod.plan_por_clave(config.plan_actual),
            "vendedores_adicionales": config.vendedores_adicionales,
        }
    finally:
        sesion.close()
    return plantillas.TemplateResponse("configuracion.html", {
        "request": request, "config": datos, "guardado": guardado,
    })


@app.post("/configuracion")
def guardar_configuracion(valor_dolar: float = Form(...), vendedores_adicionales: int = Form(0)):
    """Guarda el valor del dólar y los vendedores adicionales contratados."""
    sesion = Sesion()
    try:
        config = Configuracion.obtener(sesion)
        if valor_dolar > 0:
            config.valor_dolar = valor_dolar
            config.dolar_configurado = True
        config.vendedores_adicionales = max(0, vendedores_adicionales)
        sesion.commit()
    finally:
        sesion.close()
    return RedirectResponse(url="/configuracion?guardado=true", status_code=303)
