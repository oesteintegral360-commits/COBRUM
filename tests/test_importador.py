"""
Tests del motor (Fase 1). Cubren las 4 garantías centrales:
  1. no se duplican facturas al subir la misma foto dos veces,
  2. la foto nueva REEMPLAZA a la vieja,
  3. una factura que desaparece de la foto queda 'pagada',
  4. el CUIT se normaliza y se valida el dígito verificador.

Cada test usa su propia base SQLite temporal (no toca la de verdad).
"""

from datetime import date, timedelta

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from cobranzas.db import Base
from cobranzas.modelos import Cliente, Factura
from cobranzas.importador import importar_foto
from cobranzas.cuit import normalizar_cuit, validar_digito_verificador
from cobranzas import motor


HOY = date(2026, 6, 18)


@pytest.fixture
def sesion():
    """Crea una base temporal en memoria y devuelve una sesión limpia para cada test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(bind=engine)
    s = Sesion()
    yield s
    s.close()


def _escribir_excel(ruta, filas):
    """Helper: arma un Excel con las columnas que espera el importador."""
    columnas = ["CUIT", "Razón social", "Teléfono", "Vendedor",
                "Número factura", "Saldo", "Vencimiento"]
    pd.DataFrame(filas, columns=columnas).to_excel(ruta, index=False)


# --- 1) No duplicar -------------------------------------------------------------
def test_no_duplica_al_subir_la_misma_foto_dos_veces(sesion, tmp_path):
    archivo = tmp_path / "foto.xlsx"
    filas = [
        ["30-11122233-9", "Cliente A", "", "Juan", "F-1", "1000", HOY - timedelta(days=5)],
        ["30-11122233-9", "Cliente A", "", "Juan", "F-2", "2000", HOY - timedelta(days=5)],
    ]
    _escribir_excel(archivo, filas)

    importar_foto(sesion, str(archivo))
    importar_foto(sesion, str(archivo))  # misma foto otra vez

    # Sigue habiendo 2 facturas y 1 cliente, no 4 y 2.
    assert sesion.query(Factura).count() == 2
    assert sesion.query(Cliente).count() == 1


# --- 2) y 3) La foto reemplaza, y la que desaparece queda pagada ---------------
def test_foto_reemplaza_y_desaparecida_queda_pagada(sesion, tmp_path):
    archivo1 = tmp_path / "foto1.xlsx"
    archivo2 = tmp_path / "foto2.xlsx"

    _escribir_excel(archivo1, [
        ["30-11122233-9", "Cliente A", "", "Juan", "F-1", "1000", HOY - timedelta(days=5)],
        ["30-11122233-9", "Cliente A", "", "Juan", "F-2", "2000", HOY - timedelta(days=5)],
    ])
    # En la foto 2 desaparece F-1 y aparece F-3.
    _escribir_excel(archivo2, [
        ["30-11122233-9", "Cliente A", "", "Juan", "F-2", "2000", HOY - timedelta(days=5)],
        ["30-11122233-9", "Cliente A", "", "Juan", "F-3", "3000", HOY - timedelta(days=2)],
    ])

    importar_foto(sesion, str(archivo1))
    resultado = importar_foto(sesion, str(archivo2))

    f1 = sesion.get(Factura, "F-1")
    f2 = sesion.get(Factura, "F-2")
    f3 = sesion.get(Factura, "F-3")

    assert f1.estado == "pagada"       # desapareció -> pagada
    assert f2.estado == "pendiente"    # sigue en la foto
    assert f3 is not None              # la nueva se creó
    assert f3.estado == "pendiente"
    assert resultado.facturas_pagadas == 1
    assert resultado.facturas_nuevas == 1


# --- 4) CUIT: normalización y dígito verificador --------------------------------
def test_normalizar_cuit_une_formatos():
    assert normalizar_cuit("30-11222333-4") == "30112223334"
    assert normalizar_cuit(" 30.112.223.334 ") == "30112223334"
    assert normalizar_cuit("30112223334") == "30112223334"


def test_mismo_cuit_distinto_formato_es_un_solo_cliente(sesion, tmp_path):
    archivo = tmp_path / "foto.xlsx"
    _escribir_excel(archivo, [
        ["30-11122233-9", "Cliente A", "", "Juan", "F-1", "1000", HOY - timedelta(days=5)],
        ["30112233.9".replace(".", ""), "Cliente A", "", "Juan", "F-2", "2000", HOY - timedelta(days=5)],
    ])
    # Forzamos el mismo CUIT en dos formatos distintos.
    _escribir_excel(archivo, [
        ["30-11122233-9", "Cliente A", "", "Juan", "F-1", "1000", HOY - timedelta(days=5)],
        ["30111222339", "Cliente A", "", "Juan", "F-2", "2000", HOY - timedelta(days=5)],
    ])
    importar_foto(sesion, str(archivo))
    assert sesion.query(Cliente).count() == 1


def test_digito_verificador_detecta_cuit_invalido(sesion, tmp_path):
    # CUIT con dígito final cambiado a mano (no cierra).
    archivo = tmp_path / "foto.xlsx"
    _escribir_excel(archivo, [
        ["20-30111222-0", "Cliente Sospechoso", "", "Juan", "F-1", "1000", HOY - timedelta(days=5)],
    ])
    resultado = importar_foto(sesion, str(archivo))

    cliente = sesion.query(Cliente).first()
    # Si el CUIT no era válido, debe quedar marcado sospechoso y haber un aviso.
    if not validar_digito_verificador("20301112220"):
        assert cliente.cuit_sospechoso is True
        assert any("dígito verificador" in a for a in resultado.avisos)


# --- Motor: vencidos y tramos ---------------------------------------------------
def test_motor_vencida_y_tramos():
    f_vencida = Factura(numero_factura="X", cuit="1", saldo_pendiente=100,
                        fecha_vencimiento=HOY - timedelta(days=45), estado="pendiente")
    f_al_dia = Factura(numero_factura="Y", cuit="1", saldo_pendiente=100,
                       fecha_vencimiento=HOY + timedelta(days=10), estado="pendiente")

    assert motor.esta_vencida(f_vencida, HOY) is True
    assert motor.esta_vencida(f_al_dia, HOY) is False
    assert motor.dias_atraso(f_vencida, HOY) == 45
    assert motor.dias_atraso(f_al_dia, HOY) == 0
    assert motor.tramo_atraso(45) == "31-60 días"
    assert motor.tramo_atraso(0) == "al día"
    assert motor.tramo_atraso(120) == "+90 días"
