"""
Tests de la tanda de Precios:
  - la conversión de USD a pesos usa el dólar configurable (nunca pesos fijos),
  - el precio anual da 2 meses gratis,
  - los límites del plan avisan cuando se superan (y el add-on suma asientos).
"""

from decimal import Decimal

from cobranzas import planes as p


def test_precio_en_pesos_usa_el_dolar_configurable():
    arranque = p.plan_por_clave("arranque")
    # 79 USD a un dólar de 1000 -> 79.000 pesos.
    assert arranque.precio_en_pesos(1000) == Decimal("79000")
    # A otro dólar, otro precio (no es fijo).
    assert arranque.precio_en_pesos(1500) == Decimal("118500")


def test_precio_anual_da_dos_meses_gratis():
    crecimiento = p.plan_por_clave("crecimiento")
    # 149 * (12 - 2) = 1490.
    assert crecimiento.precio_anual_usd() == 1490


def test_planes_basicos():
    claves = [pl.clave for pl in p.PLANES]
    assert claves == ["arranque", "crecimiento", "pro"]
    assert p.plan_por_clave("crecimiento").destacado is True
    # Pro es ilimitado.
    pro = p.plan_por_clave("pro")
    assert pro.max_vendedores is None and pro.max_clientes is None
    assert pro.permite_addon is False


def test_limite_de_vendedores_avisa():
    arranque = p.plan_por_clave("arranque")  # tope 3 vendedores
    # 3 vendedores: dentro del plan, sin avisos.
    assert p.chequear_limites(arranque, 3, 10) == []
    # 4 vendedores: se pasa, avisa.
    avisos = p.chequear_limites(arranque, 4, 10)
    assert len(avisos) == 1 and "vendedor" in avisos[0]


def test_addon_suma_asientos_de_vendedor():
    arranque = p.plan_por_clave("arranque")  # tope 3
    # Con 2 vendedores adicionales, el tope sube a 5: 5 está OK.
    assert p.chequear_limites(arranque, 5, 10, vendedores_adicionales=2) == []
    # 6 ya se pasa.
    assert len(p.chequear_limites(arranque, 6, 10, vendedores_adicionales=2)) == 1


def test_limite_de_clientes_avisa():
    arranque = p.plan_por_clave("arranque")  # tope 150 clientes
    assert p.chequear_limites(arranque, 1, 150) == []
    avisos = p.chequear_limites(arranque, 1, 151)
    assert len(avisos) == 1 and "clientes" in avisos[0]


def test_pro_no_tiene_limites():
    pro = p.plan_por_clave("pro")
    # Aunque tenga miles, Pro no avisa nada.
    assert p.chequear_limites(pro, 999, 999999) == []
