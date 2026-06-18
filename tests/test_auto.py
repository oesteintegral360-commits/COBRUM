"""
Tests del modo automático (Fase 3): el sistema manda solo los recordatorios que
corresponden, sin tocar botón, y con freno anti-spam.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cobranzas.db import Base
from cobranzas.modelos import Cliente, Factura, Mensaje
from cobranzas import auto

HOY = date(2026, 6, 18)


@pytest.fixture
def sesion():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _cliente_con_factura(sesion, cuit, dias_vencida, saldo=10000, ultimo_entrante=None):
    sesion.add(Cliente(cuit=cuit, nombre=f"Cliente {cuit}", vendedor_asignado="Juan",
                       ultimo_mensaje_entrante=ultimo_entrante))
    sesion.add(Factura(numero_factura=f"F-{cuit}", cuit=cuit, saldo_pendiente=saldo,
                       fecha_vencimiento=HOY - timedelta(days=dias_vencida), estado="pendiente"))
    sesion.commit()


def test_manda_solo_a_los_que_tienen_vencidas(sesion):
    _cliente_con_factura(sesion, "1", dias_vencida=10)    # vencida -> le manda
    _cliente_con_factura(sesion, "2", dias_vencida=-5)    # no vencida -> no le manda
    resumen = auto.ejecutar_cobranza(sesion, HOY)
    assert resumen["enviados"] == 1
    # Se registró un saliente para el cliente 1 y ninguno para el 2.
    assert sesion.query(Mensaje).filter_by(cuit="1", direccion="saliente").count() == 1
    assert sesion.query(Mensaje).filter_by(cuit="2", direccion="saliente").count() == 0


def test_anti_spam_no_reescribe_si_ya_le_escribimos_hace_poco(sesion):
    _cliente_con_factura(sesion, "1", dias_vencida=10)
    # Ya le mandamos algo hace 1 hora.
    sesion.add(Mensaje(cuit="1", direccion="saliente", tipo="plantilla",
                       fecha_hora=datetime.now() - timedelta(hours=1), texto="hola"))
    sesion.commit()
    resumen = auto.ejecutar_cobranza(sesion, HOY)
    assert resumen["enviados"] == 0
    assert resumen["salteados"] == 1


def test_usa_la_ventana_para_marcar_gratis(sesion):
    # Respondió hace 1 hora -> ventana abierta -> el saliente es gratis.
    _cliente_con_factura(sesion, "1", dias_vencida=10,
                         ultimo_entrante=datetime.now() - timedelta(hours=1))
    resumen = auto.ejecutar_cobranza(sesion, HOY)
    assert resumen["enviados"] == 1
    assert resumen["gratis"] == 1 and resumen["plantillas"] == 0


def test_sin_ventana_es_plantilla(sesion):
    _cliente_con_factura(sesion, "1", dias_vencida=10)  # nunca respondió
    resumen = auto.ejecutar_cobranza(sesion, HOY)
    assert resumen["plantillas"] == 1 and resumen["gratis"] == 0
