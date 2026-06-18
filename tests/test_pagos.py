"""
Tests del link de pago "de un toque" (Fase 5, simulado):
  - se crea un link pendiente,
  - al pagar se salda la deuda, se registra el cobro acreditado y el cliente sale de la cobranza,
  - el link no se puede pagar dos veces.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cobranzas.db import Base
from cobranzas.modelos import Cliente, Cobro, LinkPago
from cobranzas import pagos


@pytest.fixture
def sesion():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _cliente(sesion, cuit="1", vendedor="Juan"):
    c = Cliente(cuit=cuit, nombre="Cliente", vendedor_asignado=vendedor)
    sesion.add(c)
    sesion.commit()
    return c


def test_crear_link_queda_pendiente(sesion):
    c = _cliente(sesion)
    link = pagos.crear_link(sesion, c, 10000)
    assert link.estado == "pendiente"
    assert pagos.url_de(link.token).endswith(link.token)


def test_pagar_salda_la_deuda_y_registra_cobro_acreditado(sesion):
    c = _cliente(sesion)
    link = pagos.crear_link(sesion, c, 10000)

    ok = pagos.registrar_pago_link(sesion, link.token)
    assert ok is True

    # El link quedó pagado.
    assert sesion.get(LinkPago, link.token).estado == "pagado"
    # Se registró un cobro acreditado, con el método 'link' y el vendedor del cliente.
    cobro = sesion.query(Cobro).filter_by(metodo="link").one()
    assert cobro.estado == "acreditado"
    assert cobro.vendedor == "Juan"
    assert float(cobro.monto) == 10000
    # El cliente sale de la cobranza.
    assert sesion.get(Cliente, "1").estado_gestion == "pagado"


def test_no_se_paga_dos_veces(sesion):
    c = _cliente(sesion)
    link = pagos.crear_link(sesion, c, 5000)
    assert pagos.registrar_pago_link(sesion, link.token) is True
    assert pagos.registrar_pago_link(sesion, link.token) is False
    # Solo quedó un cobro.
    assert sesion.query(Cobro).count() == 1


def test_link_inexistente_no_rompe(sesion):
    assert pagos.registrar_pago_link(sesion, "token-que-no-existe") is False


def test_agregar_link_al_mensaje_incluye_la_url(sesion):
    c = _cliente(sesion)
    texto = pagos.agregar_link_al_mensaje(sesion, c, 8000, "Hola, te debo plata", "Distri del Oeste")
    assert "Distri del Oeste" in texto
    assert "/pagar/" in texto
    # Se creó el link en la base.
    assert sesion.query(LinkPago).count() == 1
