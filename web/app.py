"""
La web de COBRUM (Fase 1): subir la foto (Excel) y ver la lista.

Es a propósito mínima y "acción-first": una sola acción importante por pantalla.
  - GET  /         -> pantalla de inicio con el botón grande "Subir foto".
  - POST /subir    -> recibe el Excel, lo importa y redirige a la lista.
  - GET  /clientes -> la lista de clientes con sus facturas, vencidos y tramos.
"""

from datetime import date, datetime
from pathlib import Path
import shutil

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from cobranzas.db import Sesion, crear_tablas
from cobranzas.modelos import Cliente, ImportSnapshot, Configuracion, Mensaje
from cobranzas.importador import importar_foto
from cobranzas import motor
from cobranzas import planes as planes_mod
from cobranzas import mensajeria

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

            # Datos para la agenda priorizada (Fase 2).
            vencidas = [f for f in facturas if motor.esta_vencida(f, hoy)]
            total_vencido = sum((float(f.saldo_pendiente) for f in vencidas), 0.0)
            max_dias = max((motor.dias_atraso(f, hoy) for f in vencidas), default=0)
            puntaje = motor.puntaje_cobrabilidad(facturas, hoy)
            tiene_vencidas = len(vencidas) > 0

            # Prioridad por color, según hace cuánto está la más vencida.
            if max_dias > 60:
                prioridad = "alta"
            elif max_dias > 30:
                prioridad = "media"
            elif max_dias >= 1:
                prioridad = "baja"
            else:
                prioridad = None

            # Razón en una línea (texto humano).
            if tiene_vencidas:
                razon = (f"Debe ${total_vencido:,.0f} vencidos · la más vieja hace "
                         f"{max_dias} días").replace(",", ".")
            else:
                proxima = min((f.fecha_vencimiento for f in facturas
                               if f.estado == "pendiente"), default=None)
                razon = ("Todavía no venció" + (f" · vence {proxima.strftime('%d/%m')}"
                         if proxima else ""))

            tarjetas.append({
                "cuit": c.cuit,
                "nombre": c.nombre or "(sin nombre)",
                "vendedor": c.vendedor_asignado or "",
                "falta_telefono": c.falta_telefono,
                "cuit_sospechoso": c.cuit_sospechoso,
                "total": float(total),
                "total_vencido": total_vencido,
                "max_dias": max_dias,
                "puntaje": puntaje,
                "tiene_vencidas": tiene_vencidas,
                "prioridad": prioridad,
                "razon": razon,
                "facturas": facturas_info,
            })

        # Agenda = los que tienen vencidas, ordenados por puntaje (lo más cobrable hoy).
        agenda = sorted([t for t in tarjetas if t["tiene_vencidas"]],
                        key=lambda t: t["puntaje"], reverse=True)
        # Próximos = con deuda pero sin vencidas todavía, ordenados por su vencimiento.
        proximos = sorted([t for t in tarjetas if not t["tiene_vencidas"]],
                          key=lambda t: t["max_dias"], reverse=True)

        # --- Días de cobranza (DSO aprox) + tendencia vs la foto anterior ---
        ultimos = (sesion.query(ImportSnapshot)
                   .order_by(ImportSnapshot.id.desc()).limit(2).all())
        dso_actual = ultimos[0].dso_aprox if ultimos else 0
        dso_previo = ultimos[1].dso_aprox if len(ultimos) > 1 else None
        snapshot = None
        if ultimos:
            snapshot = {
                "nombre_archivo": ultimos[0].nombre_archivo,
                "cantidad_facturas": ultimos[0].cantidad_facturas,
                "total_pendiente": float(ultimos[0].total_pendiente),
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

        # --- Contador de costo de WhatsApp: plantillas enviadas este mes ---
        inicio_mes = datetime(hoy.year, hoy.month, 1)
        plantillas_mes = (sesion.query(Mensaje)
                          .filter(Mensaje.direccion == "saliente",
                                  Mensaje.tipo == "plantilla",
                                  Mensaje.fecha_hora >= inicio_mes).count())
        costo_usd = plantillas_mes * mensajeria.COSTO_PLANTILLA_USD
        costo_pesos = costo_usd * float(config.valor_dolar)
    finally:
        sesion.close()

    return plantillas.TemplateResponse("lista.html", {
        "request": request,
        "agenda": agenda,
        "proximos": proximos,
        "tiene_algo": bool(agenda or proximos),
        "resultado": _ultimo_resultado["datos"],
        "snapshot": snapshot,
        "dso_actual": dso_actual,
        "dso_previo": dso_previo,
        "hoy": hoy,
        "avisos_limite": avisos_limite,
        "plan_actual": plan,
        "plantillas_mes": plantillas_mes,
        "costo_pesos": costo_pesos,
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
            "nombre_negocio": config.nombre_negocio,
        }
    finally:
        sesion.close()
    return plantillas.TemplateResponse("configuracion.html", {
        "request": request, "config": datos, "guardado": guardado,
    })


@app.post("/configuracion")
def guardar_configuracion(valor_dolar: float = Form(...), vendedores_adicionales: int = Form(0),
                          nombre_negocio: str = Form("")):
    """Guarda el valor del dólar, los vendedores adicionales y el nombre del negocio."""
    sesion = Sesion()
    try:
        config = Configuracion.obtener(sesion)
        if valor_dolar > 0:
            config.valor_dolar = valor_dolar
            config.dolar_configurado = True
        config.vendedores_adicionales = max(0, vendedores_adicionales)
        if nombre_negocio.strip():
            config.nombre_negocio = nombre_negocio.strip()
        sesion.commit()
    finally:
        sesion.close()
    return RedirectResponse(url="/configuracion?guardado=true", status_code=303)


def _datos_cliente(sesion, cuit, hoy):
    """
    Junta lo que necesita la pantalla de conversación de un cliente: sus datos, la deuda
    vencida, en qué etapa de tono va, si la ventana de 24 hs está abierta, el texto del
    próximo recordatorio y el historial de mensajes. Devuelve None si el cliente no existe.
    """
    cliente = sesion.get(Cliente, cuit)
    if cliente is None:
        return None

    config = Configuracion.obtener(sesion)
    facturas = list(cliente.facturas)
    vencidas = [f for f in facturas if motor.esta_vencida(f, hoy)]
    total_vencido = sum((float(f.saldo_pendiente) for f in vencidas), 0.0)
    max_dias = max((motor.dias_atraso(f, hoy) for f in vencidas), default=0)
    # La factura más vieja vencida (la que nombramos en el mensaje).
    factura_ref = ""
    if vencidas:
        factura_ref = max(vencidas, key=lambda f: motor.dias_atraso(f, hoy)).numero_factura

    ahora = datetime.now()
    etapa = mensajeria.etapa_por_dias(max_dias)
    ventana = mensajeria.ventana_abierta(cliente.ultimo_mensaje_entrante, ahora)
    tipo_proximo = mensajeria.tipo_de_mensaje(cliente.ultimo_mensaje_entrante, ahora)

    propuesta = ""
    if vencidas:
        propuesta = mensajeria.redactar_recordatorio(
            cliente.nombre or "cliente", config.nombre_negocio, cliente.vendedor_asignado,
            factura_ref, total_vencido, max_dias, etapa)

    historial = (sesion.query(Mensaje).filter(Mensaje.cuit == cuit)
                 .order_by(Mensaje.fecha_hora.asc(), Mensaje.id.asc()).all())
    mensajes = [{
        "direccion": m.direccion,
        "texto": m.texto,
        "tipo": m.tipo,
        "etapa": m.etapa,
        "fecha_hora": m.fecha_hora,
    } for m in historial]

    return {
        "cuit": cliente.cuit,
        "nombre": cliente.nombre or "(sin nombre)",
        "vendedor": cliente.vendedor_asignado or "",
        "telefono": cliente.telefono_whatsapp or "",
        "falta_telefono": cliente.falta_telefono,
        "total_vencido": total_vencido,
        "tiene_vencidas": bool(vencidas),
        "etapa": etapa,
        "ventana_abierta": ventana,
        "tipo_proximo": tipo_proximo,
        "propuesta": propuesta,
        "mensajes": mensajes,
        "botones": mensajeria.BOTONES,
    }


@app.get("/cliente/{cuit}", response_class=HTMLResponse)
def pagina_cliente(request: Request, cuit: str):
    """Conversación con un cliente: ver el recordatorio propuesto, enviarlo y simular respuestas."""
    sesion = Sesion()
    try:
        datos = _datos_cliente(sesion, cuit, date.today())
    finally:
        sesion.close()
    if datos is None:
        return RedirectResponse(url="/clientes", status_code=303)
    return plantillas.TemplateResponse("cliente.html", {"request": request, "c": datos})


@app.post("/cliente/{cuit}/enviar")
def enviar_recordatorio(cuit: str):
    """Registra el envío (simulado) del recordatorio propuesto, marcando si es plantilla o gratis."""
    hoy = date.today()
    sesion = Sesion()
    try:
        datos = _datos_cliente(sesion, cuit, hoy)
        if datos and datos["tiene_vencidas"]:
            sesion.add(Mensaje(
                cuit=cuit,
                direccion="saliente",
                tipo=datos["tipo_proximo"],   # 'plantilla' (con costo) o 'respuesta_ventana' (gratis)
                etapa=datos["etapa"],
                fecha_hora=datetime.now(),
                texto=datos["propuesta"],
            ))
            sesion.commit()
    finally:
        sesion.close()
    return RedirectResponse(url=f"/cliente/{cuit}", status_code=303)


@app.post("/cliente/{cuit}/responder")
def responder_cliente(cuit: str, boton: str = Form(...)):
    """
    Simula que el cliente toca uno de los 3 botones. Cuenta como mensaje ENTRANTE y abre
    la ventana gratis de 24 hs.
    """
    sesion = Sesion()
    try:
        cliente = sesion.get(Cliente, cuit)
        if cliente is not None and boton in mensajeria.BOTONES:
            ahora = datetime.now()
            sesion.add(Mensaje(
                cuit=cuit, direccion="entrante", fecha_hora=ahora, texto=boton,
            ))
            cliente.ultimo_mensaje_entrante = ahora  # abre la ventana gratis
            sesion.commit()
    finally:
        sesion.close()
    return RedirectResponse(url=f"/cliente/{cuit}", status_code=303)
