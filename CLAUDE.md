# COBRUM — Instrucciones para Claude

## Sobre el usuario
Soy **no-técnico**. No supongas que sé instalar herramientas, crear cuentas, encontrar opciones en interfaces, o usar la terminal.

## Regla #1 — Cada vez que me pidas algo, dame los pasos exactos

Cuando me pidas que haga **cualquier acción fuera del chat** (instalar algo, crear una cuenta, configurar un servicio, ir a una página, ejecutar un comando, copiar/pegar algo, etc.), siempre incluí:

1. **El comando exacto** a copiar/pegar — si es terminal, ponelo en un bloque de código listo para pegar.
2. **La URL exacta** — si es una página web, dame el link directo (https://...), no me digas "andá a la web de X".
3. **Los pasos numerados** describiendo qué botón clickear, qué campo llenar, qué seleccionar — como si me lo mostraras con el dedo.
4. **Qué esperar como resultado** — qué tengo que ver en pantalla para saber que salió bien.
5. **Cómo confirmar que funcionó** — un comando o señal visual concreta.

Si la acción requiere decisiones (ej: elegir una región, un plan, un nombre), decime cuál elegir y por qué — no me dejes a mí adivinando.

Si hay riesgo de que algo falle (ej: "si te aparece tal error, hacé tal cosa"), avisame antes, no después.

## Regla #2 — Idioma
Todo el código (variables, funciones, comentarios) y comunicación en **español**.

## Regla #3 — Filosofía de diseño: "App intuitiva como las grandes"

La app tiene que sentirse como **Instagram, Facebook, WhatsApp**: cualquier persona la abre por primera vez y entiende qué hacer sin instrucciones. Tiene que verse y funcionar bien en **cualquier dispositivo** (computadora o celular) — diseño responsive. **NO copiar diseños directamente** — heredar los principios que las hacen funcionar.

### Principios a aplicar siempre

1. **Una sola acción posible por pantalla.** Si hay más de un botón importante, uno es claramente primario (color fuerte) y los otros secundarios (sutiles). El usuario nunca duda qué hacer.

2. **Zonas tocables/clickeables amplias.** Botones grandes y cómodos, con buen espaciado. Lo más importante, bien a la vista y fácil de accionar tanto con mouse como con el dedo.

3. **Feedback inmediato.** Cada acción produce una reacción visual instantánea: el botón cambia de color, aparece un loader, una animación corta. El usuario nunca duda si su acción se registró.

4. **Texto humano, no técnico.** "Tu foto se procesó ✓" en vez de "Operación exitosa". "¿Subís otra foto?" en vez de "Confirmar acción". Cero jerga técnica.

5. **Cero formularios largos.** Pedir lo mínimo. Si hacen falta varios datos, en pasos cortos uno a la vez con barra de progreso, NUNCA un formulario gigante.

6. **Patrones reconocibles, no creatividad gratuita.** Si el usuario lo conoce de otra app, funciona igual acá.

7. **Imágenes y señales visuales antes que texto.** Estado por color (verde/amarillo/rojo), cada cliente como una mini-card. La pantalla se **escanea con los ojos en 2 segundos**, no se lee.

8. **Cero estados vacíos sin ayuda.** Si no hay nada para mostrar, no decir "Sin datos" — decir "Subí tu primera foto" con una ilustración y un botón grande. Cada vacío es una invitación a la próxima acción.

9. **Animaciones cortas (150-250ms) pero presentes.** Transiciones suaves. Nunca cambios bruscos.

10. **Skeleton screens, no spinners** (cuando aplique). Mientras carga, mostrar la estructura grisada de lo que viene, no un círculo girando aislado.

### Cómo aplicarlo en cada decisión

- **Antes de escribir código de una pantalla**, preguntate: *"¿Mi abuela podría usar esto sin que le explique?"* Si la respuesta es no, simplificar.
- **Cuando dudes entre dos diseños**, elegí el que se parezca más a una app que el usuario ya usa todos los días.
- **Si una pantalla tiene más de un foco visual**, dividila en dos pantallas separadas.
- **Si una decisión es entre "más features" y "más simple"**, ganar simple. Siempre.

## Principios de diseño del producto (decisiones permanentes — NO cambian entre sesiones)

Estos puntos salieron de la investigación de mercado (HighRadius, Upflow, Chaser, Cobrix) y son decisiones de producto que mandan aunque algunas funciones todavía estén simuladas o por construir:

1. **Diseñar pensando en el costo de WhatsApp.** La API oficial cobra por cada mensaje de **plantilla**; pero cuando el cliente responde se abre una **ventana de 24 hs** donde los mensajes salientes son **gratis**. La lógica debe **preferir responder dentro de la ventana**. Llevar registro por cliente de si hay ventana abierta (timestamp del último mensaje entrante) y marcar cada saliente como `plantilla` (con costo) o `respuesta_ventana` (gratis). Mostrar un contador de plantillas enviadas (costo estimado) para tener visibilidad del gasto.

2. **Los botones interactivos son clave (no solo UX).** Cada mensaje lleva 3 botones: **"Ya pagué" / "Pido unos días" / "Tengo un reclamo"**. Además de ordenar la conversación, cuando el cliente toca un botón **cuenta como mensaje entrante y abre la ventana gratis** del punto 1.

3. **Secuencia de mensajes con tono escalonado** (configurable): Etapa 1 (recién vencida) amable, asumir olvido, con el medio de pago → Etapa 2 (sigue impaga) ofrecer alternativa/coordinar → Etapa 3 (varios días) fecha concreta + consecuencia clara. **Nunca arrancar con tono duro ni amenazas.**

4. **Identidad del envío.** Los mensajes salen a nombre del **vendedor / del negocio** (el cliente ve el nombre de la empresa, no el de la plataforma) — configurable. Si un cliente no tiene WhatsApp, el recordatorio iría por **email como respaldo**.

5. **Diferenciadores a proteger (NO perder).** Existe un competidor casi idéntico (Cobrix) que hace recordatorios centralizados por WhatsApp. Lo que nos diferencia: (a) el modelo está **centrado en el VENDEDOR** — agenda diaria por vendedor, cuentas asignadas; y (b) el loop de reventa "reestockeate con [vendedor]" (futuro). **NO derivar el producto hacia un simple enviador centralizado de recordatorios.** El modelo de datos y la lógica mantienen al vendedor en el centro.

6. **Confirmación de pago según el método.** **Transferencia/depósito** → comprobante + **cruce contra el extracto bancario**. **Efectivo** → lo confirma el **vendedor** (encaja con "vendedor en el centro"): la plata queda **"a rendir"** hasta que la entrega/deposita (**"rendido"**). COBRUM sigue la **"plata en la calle"** por vendedor (cobrado ≠ rendido). **Link de pago "de un toque"** (Fase 5, simulado): el mensaje lleva un link y el cliente salda de un toque; **la plata va a la cuenta de la EMPRESA, no de COBRUM** (el día real, cada empresa conecta su propio Mercado Pago vía OAuth y COBRUM solo arma el link y escucha el webhook de pago). El pago online queda `Cobro` método `link`, estado `acreditado` (confirmado, no hace falta conciliar).

## Precios (decisiones permanentes)

**Principio que manda:** los precios se definen en **USD** y se cobran en **pesos** al valor del
dólar del día. **NUNCA se guardan pesos fijos** (con la inflación se desactualizan solos): el
peso se calcula al vuelo = `precio_usd * valor_dolar` configurable. El modelo es **suscripción
mensual + cobro por vendedor (asiento)**.

**Los 3 planes** (la fuente de verdad en código es `cobranzas/planes.py`):
- **Arranque — USD 79/mes.** Hasta 3 vendedores · hasta 150 clientes activos · 1 admin.
- **Crecimiento — USD 149/mes.** Marcado como **"El más elegido"**. Hasta 8 vendedores · hasta
  600 clientes activos · admins múltiples.
- **Pro — desde USD 299/mes.** Vendedores y clientes ilimitados (uso razonable).
- **Add-on** (Arranque y Crecimiento): vendedor adicional **USD 19/mes** c/u. En Pro no aplica.
- **Anual:** 2 meses gratis al pagar el año completo.

**La app respeta los límites** (vendedores y clientes activos): si se superan, **avisa y sugiere**
sumar el add-on o subir de plan — **nunca bloquea** el acceso a los datos.

**Costo/margen:** referencia interna en `pricing-notes.md` (NO se muestra al cliente).

> El **login / cuentas / multi-empresa** y el **cobro real** (Mercado Pago u otro) son parte del
> hito "ponerlo online como SaaS" (mudanza a la nube), no de esta tanda. La base ya está
> preparada para esa mudanza (ver Stack: `DATABASE_URL`).

## Stack y decisiones técnicas
- **Python** (hoy probado en 3.9; funciona en versiones más nuevas también).
- **SQLite detrás de SQLAlchemy** — la base vive detrás de una sola línea (`DATABASE_URL` en `cobranzas/config.py`). Hoy es un archivo local; el día que comercialicemos se cambia esa línea por **PostgreSQL** en la nube **sin reescribir la lógica**.
- **FastAPI + Jinja2 + Tailwind (CDN)** — web liviana tipo app, **sin paso de build**.
- **pandas + openpyxl** para leer Excel (el corazón del producto).
- Pantalla **acción-first** (a quién cobrar / estado), NO un panel de reportes.

### El producto en una frase
COBRUM es una **"capa de acción"** sobre el sistema contable que la empresa ya tiene: recibe una "foto" en Excel de quién-debe-qué, decide a quién perseguir, le habla al cliente por WhatsApp en nombre del vendedor y marca la factura como cobrada. El norte es bajar el **DSO** (días de cobranza).

### Cómo se construye
En **5 fases**, frenando a chequear al final de cada una. Partes chicas, commits chicos, honestidad sobre la simplicidad. En cada fase: investigar lo mejor del mundo (EEUU/Europa/Asia) y proponer mejoras baratas, sin meter complejidad de más en el MVP.
- **Fase 1 (hecha): el motor.** Importar Excel, normalizar/validar CUIT, foto que reemplaza sin duplicar, calcular vencidos / días de atraso / tramos / total por cliente.
- **Fase 2 (hecha): agenda priorizada + DSO.** `puntaje_cobrabilidad` balanceado (monto + atraso) ordena "a quién cobrar hoy"; `dias_cobranza_aprox` (proxy del DSO, promedio de atraso ponderado por monto) con tendencia foto a foto guardada en `ImportSnapshot.dso_aprox`.
- **Fase 3 (hecha): mensajería WhatsApp (simulada).** Dos modos (configurable en Configuración, `Configuracion.modo_envio`): **copiloto** (el sistema propone, un humano toca "Enviar") y **automático** (el sistema manda solo los recordatorios que corresponden al subir la foto o al tocar "Ejecutar cobranza de hoy", `cobranzas/auto.py`, con freno anti-spam de 20 hs). El texto y el tono por etapa están en `cobranzas/mensajeria.py` (firmado por vendedor/negocio). Cada saliente se marca `plantilla` (con costo) o `respuesta_ventana` (gratis si hay ventana de 24 hs abierta). Los 3 botones simulan respuesta entrante y abren la ventana (`Cliente.ultimo_mensaje_entrante`). Contador de costo de plantillas del mes en la agenda. Conversación por cliente en `/cliente/{cuit}`. **Envío real 24/7 = hito SaaS** (API oficial de WhatsApp + servidor en la nube): hoy todo simulado, corre local.
- **Fase 4 (hecha): lógica de respuestas.** Cada botón cambia el `estado_gestion` del cliente (`cobranzas/respuestas.py`): "Ya pagué" → `pago_informado` (pausa, a verificar en Fase 5); "Pido unos días" → `promesa_pago` (pausa 7 días, después reaparece); "Tengo un reclamo" → `reclamo` (pausa, atención humana). La agenda separa en "Necesitan tu atención" / "Esperando" / "A quién cobrar hoy", y el modo automático no le manda a los pausados. Resolver con "Volver a gestión".
- **Fase 5 (hecha): cobros y conciliación.** Registrar cobro por método (`cobranzas/cobros.py`, modelo `Cobro`): **efectivo** → estado `a_rendir` → `rendido` (la marca el vendedor; pantalla **Caja** `/cobros` muestra la "plata en la calle" por vendedor); **transferencia** → `a_conciliar` → `conciliado` cruzando contra el extracto bancario subido (match por monto). Al registrar un cobro, el cliente pasa a `estado_gestion='pagado'` y sale de la cobranza.
