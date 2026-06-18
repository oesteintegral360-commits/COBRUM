"""
Modelos = las tablas de la base de datos.

En la Fase 1 usamos: Cliente, Factura e ImportSnapshot.
Dejamos además 'Mensaje' esbozada (un "seam") para que la mensajería de WhatsApp de la
Fase 3 enchufe sin tener que reescribir el esquema. En esta fase NO se usa.
"""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Numeric, Date, DateTime, Boolean, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from cobranzas.db import Base


class Cliente(Base):
    """
    Una empresa/persona que nos debe plata.

    OJO: el cliente NO se carga a mano. Se crea/actualiza solo a partir de la "foto"
    (el Excel), matcheado por CUIT. Ver cobranzas/importador.py.
    """

    __tablename__ = "clientes"

    # El CUIT normalizado (solo dígitos) es la identidad del cliente.
    cuit: Mapped[str] = mapped_column(String, primary_key=True)
    nombre: Mapped[str] = mapped_column(String, default="")

    # Opcionales: si no vienen en el Excel quedan vacíos (no bloquean la Fase 1).
    telefono_whatsapp: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # El vendedor es CENTRAL en este producto (la agenda es por vendedor). No es un
    # dato cosmético: es lo que nos diferencia de un enviador centralizado de mensajes.
    vendedor_asignado: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # SEAM Fase 3 (ventana de 24 hs de WhatsApp): timestamp del último mensaje que
    # ENTRÓ del cliente. Mientras está dentro de las 24 hs, responder es gratis.
    # En la Fase 1 este campo se crea pero NADIE lo escribe todavía.
    ultimo_mensaje_entrante: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Marca de calidad de dato: si el CUIT no pasa el dígito verificador, lo dejamos
    # entrar igual pero marcado para revisar (no bloquea la carga).
    cuit_sospechoso: Mapped[bool] = mapped_column(Boolean, default=False)

    facturas: Mapped[list["Factura"]] = relationship(
        back_populates="cliente", cascade="all, delete-orphan"
    )

    @property
    def falta_telefono(self) -> bool:
        """True si todavía no sabemos por dónde contactarlo (se completa antes de Fase 3)."""
        return not (self.telefono_whatsapp or "").strip()


class Factura(Base):
    """
    Una factura impaga (o que estuvo impaga). Es la unidad de la "foto".

    El número de factura es su 'DNI': sirve para NO duplicar cuando se sube una foto
    nueva. La foto nueva REEMPLAZA a la vieja, no se suma.
    """

    __tablename__ = "facturas"

    # El número de factura es único: es la clave para no duplicar.
    numero_factura: Mapped[str] = mapped_column(String, primary_key=True)

    cuit: Mapped[str] = mapped_column(ForeignKey("clientes.cuit"))
    saldo_pendiente: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    fecha_vencimiento: Mapped[date] = mapped_column(Date)

    # 'pendiente' o 'pagada'. Una factura que desaparece de la foto se asume 'pagada'.
    estado: Mapped[str] = mapped_column(String, default="pendiente")

    # ¿Apareció en la última foto que subimos? Sirve para detectar las que desaparecieron.
    presente_en_ultima_foto: Mapped[bool] = mapped_column(Boolean, default=True)

    cliente: Mapped["Cliente"] = relationship(back_populates="facturas")


class ImportSnapshot(Base):
    """
    Registro de cada carga (cada vez que se sube una foto).

    Guarda la foto-resumen: cuándo, qué archivo, cuántas facturas y cuánto se debía en
    ese momento. Más adelante (Fase 2) sirve para graficar la evolución del DSO sin
    recalcular nada a mano.
    """

    __tablename__ = "import_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime)
    nombre_archivo: Mapped[str] = mapped_column(String)
    cantidad_facturas: Mapped[int] = mapped_column(Integer, default=0)
    total_pendiente: Mapped[float] = mapped_column(Numeric(14, 2), default=0)

    # Días de cobranza aproximado en el momento de esta foto (proxy del DSO). Guardarlo
    # acá nos deja graficar la evolución sin recalcular nada a mano.
    dso_aprox: Mapped[int] = mapped_column(Integer, default=0)


class Configuracion(Base):
    """
    Configuración de la empresa (una sola fila, se crea sola la primera vez).

    Acá vive lo que el usuario fija UNA vez y la app recuerda: el valor del dólar (para
    convertir los precios de USD a pesos) y en qué plan está. NO se le vuelve a preguntar
    en cada entrada.
    """

    __tablename__ = "configuracion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # Valor del dólar para mostrar los precios en pesos. Arranca con un valor de ejemplo
    # hasta que el usuario ponga el real. 'dolar_configurado' nos dice si ya lo tocó.
    valor_dolar: Mapped[float] = mapped_column(Numeric(14, 2), default=1000)
    dolar_configurado: Mapped[bool] = mapped_column(Boolean, default=False)

    # En qué plan está la empresa (clave del plan: 'arranque' | 'crecimiento' | 'pro').
    plan_actual: Mapped[str] = mapped_column(String, default="arranque")

    # Nombre con el que salen los mensajes de WhatsApp (lo que ve el cliente). La
    # identidad del envío es del negocio/vendedor, nunca de la plataforma.
    nombre_negocio: Mapped[str] = mapped_column(String, default="Distribuidora del Oeste")

    # Asientos extra contratados con el add-on "vendedor adicional".
    vendedores_adicionales: Mapped[int] = mapped_column(Integer, default=0)

    @classmethod
    def obtener(cls, sesion) -> "Configuracion":
        """Devuelve la configuración (la crea con valores por defecto si no existe)."""
        config = sesion.get(cls, 1)
        if config is None:
            config = cls(id=1)
            sesion.add(config)
            sesion.commit()
        return config


class Mensaje(Base):
    """
    SEAM (lugar reservado) para la mensajería de WhatsApp de la Fase 3.

    La clase y la tabla se definen ahora para que la arquitectura ya contemple el costo
    de WhatsApp (plantilla = paga / respuesta dentro de la ventana de 24 hs = gratis),
    pero en la Fase 1 NO se crea ningún mensaje ni se envía nada.
    """

    __tablename__ = "mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cuit: Mapped[str] = mapped_column(ForeignKey("clientes.cuit"))

    # 'saliente' (nosotros al cliente) o 'entrante' (el cliente a nosotros).
    direccion: Mapped[str] = mapped_column(String)

    # Solo aplica a salientes: 'plantilla' (tiene costo) o 'respuesta_ventana' (gratis,
    # porque el cliente respondió hace menos de 24 hs).
    tipo: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Etapa del tono escalonado: 1 amable, 2 alternativa, 3 fecha + consecuencia.
    etapa: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    fecha_hora: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    texto: Mapped[Optional[str]] = mapped_column(String, nullable=True)
