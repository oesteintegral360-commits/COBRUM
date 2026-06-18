"""
Tests de la Fase 5 (cobros y conciliación):
  - registrar un cobro saca al cliente de la cobranza,
  - el efectivo queda 'a rendir' y se puede marcar 'rendido',
  - la transferencia queda 'a conciliar' y se cruza contra el extracto por monto.
"""

from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cobranzas.db import Base
from cobranzas.modelos import Cliente, Cobro
from cobranzas import cobros as cobros_mod
from cobranzas import respuestas

HOY = date(2026, 6, 18)


@pytest.fixture
def sesion():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _cliente(sesion, cuit="1", vendedor="Juan"):
    c = Cliente(cuit=cuit, nombre=f"Cliente {cuit}", vendedor_asignado=vendedor)
    sesion.add(c)
    sesion.commit()
    return c


def test_cobro_en_efectivo_queda_a_rendir_y_saca_de_cobranza(sesion):
    c = _cliente(sesion)
    cobro = cobros_mod.registrar_cobro(sesion, c, 10000, "efectivo")
    assert cobro.estado == "a_rendir"
    assert cobro.vendedor == "Juan"
    # El cliente deja de perseguirse.
    assert c.estado_gestion == "pagado"
    assert respuestas.cobranza_pausada(c, HOY) is True


def test_marcar_rendido(sesion):
    c = _cliente(sesion)
    cobro = cobros_mod.registrar_cobro(sesion, c, 10000, "efectivo")
    cobros_mod.marcar_rendido(sesion, cobro.id)
    assert sesion.get(Cobro, cobro.id).estado == "rendido"


def test_transferencia_queda_a_conciliar(sesion):
    c = _cliente(sesion)
    cobro = cobros_mod.registrar_cobro(sesion, c, 8500.50, "transferencia")
    assert cobro.estado == "a_conciliar"


def test_conciliacion_cruza_por_monto(sesion, tmp_path):
    c1 = _cliente(sesion, "1")
    c2 = _cliente(sesion, "2")
    cobros_mod.registrar_cobro(sesion, c1, 8500.50, "transferencia")   # está en el extracto
    cobros_mod.registrar_cobro(sesion, c2, 9999.00, "transferencia")   # NO está

    # Extracto con un solo ingreso que matchea al primero.
    extracto = tmp_path / "extracto.xlsx"
    pd.DataFrame([
        [HOY, "Transferencia", 8500.50],
        [HOY, "Débito", -500.00],
    ], columns=["Fecha", "Detalle", "Monto"]).to_excel(extracto, index=False)

    resultado = cobros_mod.conciliar_con_extracto(sesion, str(extracto))
    assert resultado.conciliados == 1
    assert resultado.sin_match == 1

    estados = sorted(c.estado for c in sesion.query(Cobro).all())
    assert estados == ["a_conciliar", "conciliado"]


def test_conciliacion_avisa_si_falta_columna_de_monto(sesion, tmp_path):
    extracto = tmp_path / "raro.xlsx"
    pd.DataFrame([["a", "b"]], columns=["Cosa", "Otra"]).to_excel(extracto, index=False)
    resultado = cobros_mod.conciliar_con_extracto(sesion, str(extracto))
    assert resultado.error is not None and "importe" in resultado.error.lower()
