"""
La web de COBRUM (Fase 1): subir la foto (Excel) y ver la lista.

Es a propósito mínima y "acción-first": una sola acción importante por pantalla.
  - GET  /         -> pantalla de inicio con el botón grande "Subir foto".
  - POST /subir    -> recibe el Excel, lo importa y redirige a la lista.
  - GET  /clientes -> la lista de clientes con sus facturas, vencidos y tramos.
"""

from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote, unquote
import shutil

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from cobranzas.db import Sesion, crear_tablas
from cobranzas.modelos import Cliente, Factura, ImportSnapshot, Configuracion, Mensaje
from cobranzas.importador import importar_foto
from cobranzas import motor
from cobranzas import planes as planes_mod
from cobranzas import mensajeria
from cobranzas import auto
from cobranzas import respuestas
from cobranzas import cobros as cobros_mod
from cobranzas import pagos as pagos_mod
from cobranzas.modelos import Cobro, LinkPago

AQUI = Path(__file__).resolve().parent
SUBIDOS = AQUI / "subidos"
SUBIDOS.mkdir(exist_ok=True)

app = FastAPI(title="COBRUM")
app.mount("/static", StaticFiles(directory=AQUI / "static"), name="static")
plantillas = Jinja2Templates(directory=AQUI / "templates")


def _linkificar(texto):
    """Convierte las URLs de un texto en links clickeables (para los mensajes)."""
    import re
    from markupsafe import Markup, escape
    partes = re.split(r"(https?://\S+)", texto or "")
    salida = ""
    for i, parte in enumerate(partes):
        if i % 2 == 1:  # las posiciones impares son las URLs
            salida += f'<a href="{escape(parte)}" class="text-blue-600 underline" target="_blank">{escape(parte)}</a>'
        else:
            salida += str(escape(parte))
    return Markup(salida)


plantillas.env.filters["linkificar"] = _linkificar

# Creamos las tablas al arrancar (si no existen).
crear_tablas()

# Guardamos el último resultado de import para mostrar el resumen tras subir.
_ultimo_resultado = {"datos": None}
# Y el resumen de la última cobranza automática, para avisarle a la empresa qué se mandó solo.
_ultima_cobranza = {"resumen": None}
# Y el resultado de la última conciliación contra el extracto.
_ultima_conciliacion = {"datos": None}


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    """
    Panel de inicio (dashboard). Si todavía no hay datos, muestra la pantalla para subir
    la primera foto. Diseñado según los 4 principios: pocos KPIs claros (menos es más),
    lo importante arriba (jerarquía), tendencias en el tiempo (contexto) y color con
    intención.
    """
    hoy = date.today()
    inicio_mes = datetime(hoy.year, hoy.month, 1)
    sesion = Sesion()
    try:
        # KPI: total a cobrar (suma de lo pendiente, ahora).
        pendientes = sesion.query(Factura).filter_by(estado="pendiente").all()
        total_a_cobrar = sum(float(f.saldo_pendiente) for f in pendientes)

        # Contexto: evolución del DSO y del total a cobrar, foto a foto.
        snaps = sesion.query(ImportSnapshot).order_by(ImportSnapshot.id.asc()).all()
        etiquetas = [s.fecha_hora.strftime("%d/%m") for s in snaps]
        dso_serie = [s.dso_aprox for s in snaps]
        total_serie = [float(s.total_pendiente) for s in snaps]
        dso_actual = snaps[-1].dso_aprox if snaps else 0
        dso_previo = snaps[-2].dso_aprox if len(snaps) > 1 else None

        # KPI: cobrado este mes, y desglose por método (color con intención).
        cobros_mes = sesion.query(Cobro).filter(Cobro.fecha_hora >= inicio_mes).all()
        cobrado_mes = sum(float(c.monto) for c in cobros_mes)
        etiqueta_metodo = {"efectivo": "Efectivo", "transferencia": "Transferencia", "link": "Link de pago"}
        color_metodo = {"efectivo": "#16a34a", "transferencia": "#2563eb", "link": "#7c3aed"}
        por_metodo = {}
        for c in cobros_mes:
            por_metodo[c.metodo] = por_metodo.get(c.metodo, 0.0) + float(c.monto)
        metodo = {
            "labels": [etiqueta_metodo.get(m, m) for m in por_metodo],
            "data": [round(v) for v in por_metodo.values()],
            "colors": [color_metodo.get(m, "#64748b") for m in por_metodo],
        }

        # KPI: plata en la calle (efectivo cobrado sin rendir).
        plata_en_calle = sum(float(c.monto) for c in sesion.query(Cobro)
                             .filter(Cobro.metodo == "efectivo", Cobro.estado == "a_rendir").all())

        # KPI: clientes que necesitan atención (reclamos).
        necesitan_atencion = (sesion.query(Cliente)
                              .filter(Cliente.estado_gestion == "reclamo").count())

        hay_datos = bool(snaps or cobros_mes or total_a_cobrar > 0)
    finally:
        sesion.close()

    if not hay_datos:
        return plantillas.TemplateResponse("inicio.html", {"request": request})

    return plantillas.TemplateResponse("dashboard.html", {
        "request": request,
        "total_a_cobrar": total_a_cobrar,
        "dso_actual": dso_actual,
        "dso_previo": dso_previo,
        "cobrado_mes": cobrado_mes,
        "plata_en_calle": plata_en_calle,
        "necesitan_atencion": necesitan_atencion,
        "etiquetas": etiquetas,
        "dso_serie": dso_serie,
        "total_serie": total_serie,
        "metodo": metodo,
    })


@app.post("/subir")
async def subir(archivo: UploadFile = File(...)):
    """Recibe el Excel, lo guarda, lo importa y redirige a la lista."""
    destino = SUBIDOS / archivo.filename
    with destino.open("wb") as f:
        shutil.copyfileobj(archivo.file, f)

    sesion = Sesion()
    try:
        resultado = importar_foto(sesion, str(destino), nombre_archivo=archivo.filename)
        # Si la empresa está en modo automático, mandamos sola la cobranza de la foto nueva.
        config = Configuracion.obtener(sesion)
        if not resultado.error and config.modo_envio == "automatico":
            _ultima_cobranza["resumen"] = auto.ejecutar_cobranza(sesion, date.today())
        else:
            _ultima_cobranza["resumen"] = None
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

        # Lista completa de vendedores (para el selector) y el que está elegido (cookie).
        todos_vendedores = sorted({(c.vendedor_asignado or "").strip()
                                   for c in clientes if (c.vendedor_asignado or "").strip()})
        vendedor_sel = unquote(request.cookies.get("vendedor", ""))
        # Texto de búsqueda (por nombre o CUIT).
        busqueda = (request.query_params.get("q") or "").strip()
        q = busqueda.lower()

        # Armamos una estructura simple y ya calculada para la plantilla.
        tarjetas = []
        for c in clientes:
            # Si hay un vendedor elegido, mostramos solo SUS clientes.
            if vendedor_sel and (c.vendedor_asignado or "").strip() != vendedor_sel:
                continue
            # Si hay búsqueda, filtramos por nombre o CUIT.
            if q and q not in (c.nombre or "").lower() and q not in c.cuit:
                continue
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
                "estado_gestion": c.estado_gestion,
                "gestion_label": respuestas.resumen_estado(c, hoy),
                "esperando": respuestas.esperando_respuesta(c, hoy),
            })

        # Repartimos en grupos según el estado de gestión (Fase 4):
        #   - reclamos: necesitan atención humana.
        #   - esperando: dijo que pagó o prometió (pausa informativa).
        #   - agenda: a cobrar hoy (con vencidas, no pausados), por puntaje.
        #   - proximos: con deuda pero sin vencidas todavía.
        reclamos = [t for t in tarjetas if t["estado_gestion"] == "reclamo"]
        esperando = sorted([t for t in tarjetas
                            if t["estado_gestion"] != "reclamo" and t["esperando"]],
                           key=lambda t: t["puntaje"], reverse=True)
        agenda = sorted([t for t in tarjetas
                        if t["estado_gestion"] != "reclamo" and not t["esperando"]
                        and t["tiene_vencidas"]],
                        key=lambda t: t["puntaje"], reverse=True)
        proximos = sorted([t for t in tarjetas
                          if t["estado_gestion"] != "reclamo" and not t["esperando"]
                          and not t["tiene_vencidas"]],
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

    # El resumen de la cobranza automática se muestra una sola vez (patrón "flash").
    cobranza_flash = _ultima_cobranza["resumen"]
    _ultima_cobranza["resumen"] = None

    return plantillas.TemplateResponse("lista.html", {
        "request": request,
        "agenda": agenda,
        "proximos": proximos,
        "reclamos": reclamos,
        "esperando": esperando,
        "tiene_algo": bool(agenda or proximos or reclamos or esperando),
        "resultado": _ultimo_resultado["datos"],
        "snapshot": snapshot,
        "dso_actual": dso_actual,
        "dso_previo": dso_previo,
        "hoy": hoy,
        "avisos_limite": avisos_limite,
        "plan_actual": plan,
        "plantillas_mes": plantillas_mes,
        "costo_pesos": costo_pesos,
        "modo_envio": config.modo_envio,
        "cobranza": cobranza_flash,
        "todos_vendedores": todos_vendedores,
        "vendedor_sel": vendedor_sel,
        "volver": "/clientes",
        "busqueda": busqueda,
    })


@app.get("/filtro/vendedor")
def filtro_vendedor(v: str = "", volver: str = "/clientes"):
    """Guarda (en una cookie) qué vendedor se está viendo. v vacío = todos."""
    resp = RedirectResponse(url=volver, status_code=303)
    if v:
        resp.set_cookie("vendedor", quote(v), max_age=31_536_000)  # 1 año
    else:
        resp.delete_cookie("vendedor")
    return resp


@app.post("/cobranza/ejecutar")
def ejecutar_cobranza_ahora():
    """Manda sola, de una, la cobranza de hoy (recordatorios a quien corresponda)."""
    sesion = Sesion()
    try:
        _ultima_cobranza["resumen"] = auto.ejecutar_cobranza(sesion, date.today())
    finally:
        sesion.close()
    return RedirectResponse(url="/clientes", status_code=303)


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
            "modo_envio": config.modo_envio,
        }
    finally:
        sesion.close()
    return plantillas.TemplateResponse("configuracion.html", {
        "request": request, "config": datos, "guardado": guardado,
    })


@app.post("/configuracion")
def guardar_configuracion(valor_dolar: float = Form(...), vendedores_adicionales: int = Form(0),
                          nombre_negocio: str = Form(""), modo_envio: str = Form("copiloto")):
    """Guarda el valor del dólar, los vendedores adicionales, el nombre y el modo de envío."""
    sesion = Sesion()
    try:
        config = Configuracion.obtener(sesion)
        if valor_dolar > 0:
            config.valor_dolar = valor_dolar
            config.dolar_configurado = True
        config.vendedores_adicionales = max(0, vendedores_adicionales)
        if nombre_negocio.strip():
            config.nombre_negocio = nombre_negocio.strip()
        config.modo_envio = "automatico" if modo_envio == "automatico" else "copiloto"
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
        "estado_gestion": cliente.estado_gestion,
        "gestion_label": respuestas.resumen_estado(cliente, hoy),
        "pausada": respuestas.cobranza_pausada(cliente, hoy),
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
def enviar_recordatorio(cuit: str, texto: str = Form("")):
    """
    Registra el envío (simulado) del recordatorio. Usa el texto editado por el usuario
    (si lo cambió) o el propuesto por el sistema, y le agrega el link de pago.
    """
    hoy = date.today()
    sesion = Sesion()
    try:
        datos = _datos_cliente(sesion, cuit, hoy)
        if datos and datos["tiene_vencidas"]:
            cliente = sesion.get(Cliente, cuit)
            config = Configuracion.obtener(sesion)
            # El texto editado manda; si vino vacío, usamos el propuesto.
            base = texto.strip() or datos["propuesta"]
            # Sumamos el link de pago "de un toque" al mensaje.
            texto = pagos_mod.agregar_link_al_mensaje(
                sesion, cliente, datos["total_vencido"], base, config.nombre_negocio)
            sesion.add(Mensaje(
                cuit=cuit,
                direccion="saliente",
                tipo=datos["tipo_proximo"],   # 'plantilla' (con costo) o 'respuesta_ventana' (gratis)
                etapa=datos["etapa"],
                fecha_hora=datetime.now(),
                texto=texto,
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
            # Fase 4: el botón dispara la acción (pausar, prometer, reclamo).
            respuestas.aplicar_respuesta(cliente, boton, date.today())
            sesion.commit()
    finally:
        sesion.close()
    return RedirectResponse(url=f"/cliente/{cuit}", status_code=303)


@app.post("/cliente/{cuit}/cobro")
def registrar_cobro_cliente(cuit: str, metodo: str = Form(...), monto: float = Form(...)):
    """Registra un cobro (efectivo o transferencia) y saca al cliente de la cobranza."""
    sesion = Sesion()
    try:
        cliente = sesion.get(Cliente, cuit)
        if cliente is not None and metodo in ("efectivo", "transferencia") and monto > 0:
            cobros_mod.registrar_cobro(sesion, cliente, monto, metodo)
    finally:
        sesion.close()
    return RedirectResponse(url=f"/cliente/{cuit}", status_code=303)


@app.post("/cliente/{cuit}/datos")
def guardar_datos_cliente(cuit: str, telefono: str = Form(""), vendedor: str = Form("")):
    """Completa/edita el teléfono y el vendedor de un cliente (sin depender del Excel)."""
    sesion = Sesion()
    try:
        cliente = sesion.get(Cliente, cuit)
        if cliente is not None:
            cliente.telefono_whatsapp = telefono.strip() or None
            cliente.vendedor_asignado = vendedor.strip() or None
            sesion.commit()
    finally:
        sesion.close()
    return RedirectResponse(url=f"/cliente/{cuit}", status_code=303)


@app.post("/cliente/{cuit}/gestion")
def cambiar_gestion(cuit: str, accion: str = Form(...)):
    """Resuelve el estado de gestión: volver a gestión normal (reactivar)."""
    sesion = Sesion()
    try:
        cliente = sesion.get(Cliente, cuit)
        if cliente is not None and accion == "reactivar":
            respuestas.reactivar(cliente)
            sesion.commit()
    finally:
        sesion.close()
    return RedirectResponse(url=f"/cliente/{cuit}", status_code=303)


# --- Caja: la plata en movimiento (Fase 5) ------------------------------------

SUBIDOS_EXTRACTO = SUBIDOS  # reusamos la carpeta de subidos


@app.get("/cobros", response_class=HTMLResponse)
def pagina_cobros(request: Request):
    """Pantalla Caja: plata en la calle (a rendir) y transferencias a conciliar."""
    sesion = Sesion()
    try:
        # Lista de vendedores (para el selector) y el elegido (cookie).
        todos_vendedores = sorted({(x[0] or "").strip()
                                   for x in sesion.query(Cliente.vendedor_asignado).all()
                                   if (x[0] or "").strip()})
        vendedor_sel = unquote(request.cookies.get("vendedor", ""))

        def _es_del_vendedor(cobro):
            return not vendedor_sel or (cobro.vendedor or "").strip() == vendedor_sel

        # Efectivo a rendir, agrupado por vendedor (la "plata en la calle").
        a_rendir = [c for c in sesion.query(Cobro)
                    .filter(Cobro.metodo == "efectivo", Cobro.estado == "a_rendir")
                    .order_by(Cobro.fecha_hora.asc()).all() if _es_del_vendedor(c)]
        por_vendedor = {}
        for c in a_rendir:
            vend = c.vendedor or "Sin vendedor"
            cliente = sesion.get(Cliente, c.cuit)
            por_vendedor.setdefault(vend, {"total": 0.0, "cobros": []})
            por_vendedor[vend]["total"] += float(c.monto)
            por_vendedor[vend]["cobros"].append({
                "id": c.id,
                "cliente": cliente.nombre if cliente else c.cuit,
                "monto": float(c.monto),
                "fecha": c.fecha_hora,
            })

        # Transferencias a conciliar contra el extracto.
        a_conciliar = [c for c in sesion.query(Cobro)
                       .filter(Cobro.metodo == "transferencia", Cobro.estado == "a_conciliar")
                       .order_by(Cobro.fecha_hora.asc()).all() if _es_del_vendedor(c)]
        transferencias = []
        for c in a_conciliar:
            cliente = sesion.get(Cliente, c.cuit)
            transferencias.append({
                "cliente": cliente.nombre if cliente else c.cuit,
                "monto": float(c.monto),
                "fecha": c.fecha_hora,
            })

        total_a_rendir = sum(float(c.monto) for c in a_rendir)
        total_a_conciliar = sum(float(c.monto) for c in a_conciliar)
    finally:
        sesion.close()

    conciliacion = _ultima_conciliacion["datos"]
    _ultima_conciliacion["datos"] = None

    return plantillas.TemplateResponse("cobros.html", {
        "request": request,
        "por_vendedor": por_vendedor,
        "transferencias": transferencias,
        "total_a_rendir": total_a_rendir,
        "total_a_conciliar": total_a_conciliar,
        "conciliacion": conciliacion,
        "todos_vendedores": todos_vendedores,
        "vendedor_sel": vendedor_sel,
        "volver": "/cobros",
    })


@app.post("/cobros/rendir")
def rendir_cobro(cobro_id: int = Form(...)):
    """Marca un cobro en efectivo como rendido (el vendedor entregó la plata)."""
    sesion = Sesion()
    try:
        cobros_mod.marcar_rendido(sesion, cobro_id)
    finally:
        sesion.close()
    return RedirectResponse(url="/cobros", status_code=303)


@app.post("/cobros/conciliar")
async def conciliar_extracto(archivo: UploadFile = File(...)):
    """Sube el extracto del banco y cruza las transferencias por monto."""
    destino = SUBIDOS_EXTRACTO / f"extracto_{archivo.filename}"
    with destino.open("wb") as f:
        shutil.copyfileobj(archivo.file, f)

    sesion = Sesion()
    try:
        resultado = cobros_mod.conciliar_con_extracto(sesion, str(destino))
    finally:
        sesion.close()

    _ultima_conciliacion["datos"] = resultado
    return RedirectResponse(url="/cobros", status_code=303)


# --- Pago "de un toque" del cliente (Fase 5) — SIMULADO -----------------------

@app.get("/pagar/{token}", response_class=HTMLResponse)
def pagina_pago(request: Request, token: str):
    """Pantalla que ve el cliente al abrir el link (pago a nombre de la empresa)."""
    sesion = Sesion()
    try:
        link = sesion.get(LinkPago, token)
        if link is None:
            datos = None
        else:
            cliente = sesion.get(Cliente, link.cuit)
            config = Configuracion.obtener(sesion)
            datos = {
                "token": link.token,
                "negocio": config.nombre_negocio,
                "cliente": cliente.nombre if cliente else "",
                "monto": float(link.monto),
                "pagado": link.estado == "pagado",
            }
    finally:
        sesion.close()
    return plantillas.TemplateResponse("pago.html", {"request": request, "p": datos})


@app.post("/pagar/{token}/confirmar")
def confirmar_pago(token: str):
    """Simula que el cliente pagó: salda la deuda y registra el cobro acreditado."""
    sesion = Sesion()
    try:
        pagos_mod.registrar_pago_link(sesion, token)
    finally:
        sesion.close()
    return RedirectResponse(url=f"/pagar/{token}", status_code=303)
