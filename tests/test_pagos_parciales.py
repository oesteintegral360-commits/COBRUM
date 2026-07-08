"""
Tests de cobros parciales / pagos a cuenta (Fase 5), con foco en el anti-doble-conteo:
  - un pago parcial deja al cliente en la agenda por el resto,
  - pagar en dos veces salda la deuda,
  - tras subir una foto nueva (que ya refleja el pago), NO se descuenta dos veces.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cobranzas.db import Base
from cobranzas.modelos import Cliente, Factura, ImportSnapshot
from cobranzas import cobros as cobros_mod

HOY = date(2026, 6, 18)


@pytest.fixture
def sesion():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _cliente_con_deuda(sesion, saldo, dias_vencida=10, cuit="1"):
    c = Cliente(cuit=cuit, nombre="Cliente", vendedor_asignado="Juan")
    sesion.add(c)
    f = Factura(numero_factura=f"F-{cuit}", cuit=cuit, saldo_pendiente=saldo,
                fecha_vencimiento=HOY - timedelta(days=dias_vencida), estado="pendiente")
    sesion.add(f)
    sesion.commit()
    return c, f


def test_pago_parcial_deja_activo_y_descuenta(sesion):
    c, _ = _cliente_con_deuda(sesion, 20000)
    cobros_mod.registrar_cobro(sesion, c, 8000, "efectivo", hoy=HOY)
    # Parcial: sigue en la agenda, con el resto.
    assert c.estado_gestion == "activo"
    assert cobros_mod.saldo_vencido_pendiente(sesion, c, HOY) == 12000


def test_pago_en_dos_veces_salda(sesion):
    c, _ = _cliente_con_deuda(sesion, 20000)
    cobros_mod.registrar_cobro(sesion, c, 8000, "efectivo", hoy=HOY)
    cobros_mod.registrar_cobro(sesion, c, 12000, "efectivo", hoy=HOY)
    assert c.estado_gestion == "pagado"
    assert cobros_mod.saldo_vencido_pendiente(sesion, c, HOY) == 0


def test_pago_completo_de_una_salda(sesion):
    c, _ = _cliente_con_deuda(sesion, 20000)
    cobros_mod.registrar_cobro(sesion, c, 20000, "efectivo", hoy=HOY)
    assert c.estado_gestion == "pagado"


def test_no_se_cuenta_dos_veces_tras_nueva_foto(sesion):
    c, f = _cliente_con_deuda(sesion, 20000)
    cobro = cobros_mod.registrar_cobro(sesion, c, 8000, "efectivo", hoy=HOY)
    # Antes de una foto nueva: se descuenta el pago a cuenta.
    assert cobros_mod.saldo_vencido_pendiente(sesion, c, HOY) == 12000

    # Llega una foto nueva: el sistema contable YA reflejó el pago (la factura ahora es
    # 12000) y se registra un snapshot POSTERIOR al cobro.
    f.saldo_pendiente = 12000
    sesion.add(ImportSnapshot(fecha_hora=cobro.fecha_hora + timedelta(seconds=1),
                              nombre_archivo="foto_nueva", cantidad_facturas=1,
                              total_pendiente=12000, dso_aprox=10))
    sesion.commit()

    # El cobro quedó ANTERIOR a la foto -> no se descuenta de nuevo (no 4000).
    assert cobros_mod.cobros_desde_ultima_foto(sesion, c.cuit) == 0
    assert cobros_mod.saldo_vencido_pendiente(sesion, c, HOY) == 12000
