# COBRUM

Software de cobranzas para empresas que venden a crédito. Es una **"capa de acción"** que se
monta arriba del sistema contable que ya tenés: subís una "foto" en Excel de quién te debe qué,
y COBRUM identifica a cada cliente solo, te dice quién está vencido y hace cuánto, y (en las
fases siguientes) le habla al cliente por WhatsApp en nombre del vendedor.

Esta es la **Fase 1: el motor**. Ya funciona:
- Importás un Excel y los **clientes se identifican solos** por su CUIT (no cargás nada a mano).
- La **foto nueva reemplaza a la vieja**: las facturas no se duplican y las que desaparecen se
  asumen pagadas.
- Calcula al vuelo qué está **vencido**, hace **cuántos días** y en qué **tramo de atraso**, más
  el **total que te debe** cada cliente.

---

## Cómo correrlo en tu computadora

> Necesitás tener **Python 3** instalado. Para chequearlo, abrí la Terminal y escribí
> `python3 --version`. Si te muestra un número (ej. `Python 3.9.6`), estás listo.

Abrí la Terminal, ubicate en esta carpeta y copiá/pegá estos comandos **uno por uno**:

**1) Crear el entorno y activarlo** (esto se hace una sola vez):
```bash
python3 -m venv .venv
source .venv/bin/activate
```
Después de esto, vas a ver `(.venv)` al principio del renglón de la terminal.

**2) Instalar lo que necesita el programa** (una sola vez):
```bash
pip install -r requirements.txt
```
Esperá a que termine (puede tardar un minuto). Tiene que decir algo como
`Successfully installed ...` al final.

**3) Generar los Excel de ejemplo** (para probar sin tus datos reales):
```bash
python generar_ejemplos.py
```
Te crea `datos/ejemplos/foto_1.xlsx` y `datos/ejemplos/foto_2.xlsx`.

**4) Prender el programa:**
```bash
uvicorn web.app:app --reload
```
Tiene que aparecer un texto que dice `Uvicorn running on http://127.0.0.1:8000`.

**5) Abrir la app:** en tu navegador (Chrome, Safari), entrá a:
```
http://localhost:8000
```

---

## Probarlo (qué tenés que ver)

1. En la pantalla de inicio, tocá **"Elegí tu archivo Excel"** y elegí
   `datos/ejemplos/foto_1.xlsx`. Después tocá **"Subir foto (Excel)"**.
2. Vas a ver la lista de clientes **identificados solos**, con sus facturas, cuáles están
   vencidas, hace cuántos días y su tramo de atraso. La "Panadería La Espiga" aparece con un
   cartelito **"Revisar CUIT"** (a propósito tiene un CUIT que no cierra — el sistema avisa pero
   no te bloquea).
3. Ahora subí `datos/ejemplos/foto_2.xlsx`. Vas a ver que:
   - la factura **A-0006 es nueva** y aparece,
   - las viejas **no se duplican**,
   - la **A-0001 desapareció** de la foto, así que se asume **pagada** y ya no la perseguís.

Para **apagar** el programa: volvé a la Terminal y apretá `Ctrl + C`.

---

## Probar que todo funciona (tests automáticos)

```bash
python -m pytest
```
Tiene que decir `6 passed`. Eso confirma: no-duplicar, foto-reemplaza, desaparecida=pagada y el
manejo del CUIT (normalización + dígito verificador).

---

## Cómo está organizado (por si te da curiosidad)

```
COBRUM/
├── cobranzas/        # el "motor": toda la lógica (leer Excel, CUIT, importar, calcular)
├── web/              # la pantalla: subir el Excel y ver la lista
├── datos/ejemplos/   # los Excel de prueba
├── tests/            # los tests automáticos
└── generar_ejemplos.py
```

La base de datos es un archivo local (`datos/cobranzas.db`) que se crea solo la primera vez. El
día que pasemos a la nube, se cambia una sola línea de configuración y la lógica no se toca.
