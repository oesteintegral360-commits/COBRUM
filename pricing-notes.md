# Notas internas de precios — costo y margen

> **INTERNO. No se muestra a los clientes.** Son proyecciones para entender el margen, no
> números cerrados. Hoy WhatsApp está SIMULADO, así que el costo real actual es **0**. Las
> tarifas hay que confirmarlas con el proveedor real al integrar la API.

## Supuesto de costo
El principal costo variable es **WhatsApp**. Cada **primer mensaje de plantilla** cuesta
**~USD 0,05** (estimado, ya con markup del proveedor). Cuando el cliente responde, se abre la
**ventana de 24 hs** y los mensajes siguientes son **gratis**. El resto del costo (servidores,
etc.) es chico y casi fijo. Por eso el diseño del producto **prefiere responder dentro de la
ventana** (ver CLAUDE.md → Principios de diseño del producto, punto 1).

## Margen estimado por plan

| Plan         | Precio USD/mes | Mensajes plantilla/mes (aprox) | Costo WhatsApp | Otros | Costo total | Margen | Margen % |
|--------------|---------------:|-------------------------------:|---------------:|------:|------------:|-------:|---------:|
| Arranque     |             79 |                          ~150  |        ~USD 7,5 | ~2,5 |     ~USD 10 | ~USD 69 |    ~87% |
| Crecimiento  |            149 |                          ~600  |         ~USD 30 |  ~5  |     ~USD 35 | ~USD 114 |   ~76% |
| Pro          |            299 |                         ~1500  |         ~USD 75 | ~10  |     ~USD 85 | ~USD 214 |   ~72% |

## Modelo de cobro
- **Suscripción mensual + cobro por vendedor (asiento).** El valor crece con cada vendedor que
  usa la agenda.
- **Add-on** vendedor adicional: **USD 19/mes** c/u (aplica a Arranque y Crecimiento; en Pro no,
  porque ya es ilimitado).
- **Anual:** 2 meses gratis al pagar el año completo (pagás 10, usás 12).
- Precios en **USD**, cobrados en **pesos** al valor del dólar configurable (nunca pesos fijos).

## Pendiente al comercializar
- Confirmar la tarifa real de WhatsApp con el proveedor (BSP) elegido.
- Definir el cobro real (Mercado Pago Suscripciones u otro) — hoy no está integrado.
