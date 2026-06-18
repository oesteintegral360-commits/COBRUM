"""
Tests de la Fase 2: el puntaje de cobrabilidad (agenda priorizada) y los días de
cobranza aproximados (proxy del DSO).
"""

from datetime import date, timedelta

from cobranzas.modelos import Factura
from cobranzas import motor

HOY = date(2026, 6, 18)


def _factura(numero, saldo, dias_vencida, estado="pendiente"):
    """Crea una factura vencida hace 'dias_vencida' días (negativo = no vencida)."""
    return Factura(numero_factura=numero, cuit="1", saldo_pendiente=saldo,
                   fecha_vencimiento=HOY - timedelta(days=dias_vencida), estado=estado)


def test_puntaje_cero_si_no_hay_vencidas():
    # Factura que vence dentro de 10 días: no entra en la agenda.
    futura = _factura("F1", 10000, dias_vencida=-10)
    assert motor.puntaje_cobrabilidad([futura], HOY) == 0.0


def test_puntaje_mas_alto_con_mas_monto_y_mas_atraso():
    poco_reciente = [_factura("A", 1000, dias_vencida=5)]
    mucho_viejo = [_factura("B", 50000, dias_vencida=80)]
    assert motor.puntaje_cobrabilidad(mucho_viejo, HOY) > motor.puntaje_cobrabilidad(poco_reciente, HOY)


def test_a_igual_monto_gana_el_mas_vencido():
    reciente = [_factura("A", 10000, dias_vencida=5)]
    viejo = [_factura("B", 10000, dias_vencida=80)]
    assert motor.puntaje_cobrabilidad(viejo, HOY) > motor.puntaje_cobrabilidad(reciente, HOY)


def test_balanceado_un_monto_grande_reciente_le_gana_a_uno_chico_viejo():
    # El criterio es balanceado: un monto mucho mayor pesa, aunque sea menos viejo.
    grande_reciente = [_factura("A", 100000, dias_vencida=3)]
    chico_viejo = [_factura("B", 2000, dias_vencida=90)]
    assert motor.puntaje_cobrabilidad(grande_reciente, HOY) > motor.puntaje_cobrabilidad(chico_viejo, HOY)


def test_dias_cobranza_ponderado_por_monto():
    # 90.000 vencidos hace 100 días + 10.000 al día (0).
    # Promedio ponderado = (90000*100 + 10000*0) / 100000 = 90 días.
    facturas = [_factura("A", 90000, dias_vencida=100), _factura("B", 10000, dias_vencida=-5)]
    assert motor.dias_cobranza_aprox(facturas, HOY) == 90


def test_dias_cobranza_cero_si_todo_al_dia():
    facturas = [_factura("A", 5000, dias_vencida=-10), _factura("B", 3000, dias_vencida=0)]
    assert motor.dias_cobranza_aprox(facturas, HOY) == 0


def test_dias_cobranza_ignora_pagadas():
    facturas = [_factura("A", 90000, dias_vencida=100, estado="pagada"),
                _factura("B", 10000, dias_vencida=20)]
    # Solo cuenta la pendiente B (20 días).
    assert motor.dias_cobranza_aprox(facturas, HOY) == 20
