"""
Manejo del CUIT (la "huella digital" del cliente).

Dos funciones:
- normalizar_cuit: deja solo los dígitos, para que '30-11222333-4' y '30112223334'
  sean reconocidos como el MISMO cliente. Se aplica SIEMPRE antes de comparar.
- validar_digito_verificador: chequea que el último dígito del CUIT "cierre". Si no
  cierra, avisamos (dato sospechoso) pero NO bloqueamos la carga.
"""

import re


def normalizar_cuit(valor) -> str:
    """
    Devuelve el CUIT como solo-dígitos.

    Ejemplos:
        '30-11222333-4' -> '30112223334'
        ' 30.112.223.334 ' -> '30112223334'
    """
    if valor is None:
        return ""
    # re.sub con \D saca todo lo que NO sea dígito (guiones, puntos, espacios, etc.).
    return re.sub(r"\D", "", str(valor))


def validar_digito_verificador(cuit) -> bool:
    """
    Valida el dígito verificador de un CUIT argentino (11 dígitos).

    Devuelve True si el CUIT es válido, False si no cierra (o no tiene 11 dígitos).
    El algoritmo es el oficial: se multiplica cada uno de los primeros 10 dígitos por
    una serie fija, se suma, y de ahí sale el dígito que debería tener el final.
    """
    digitos = normalizar_cuit(cuit)
    if len(digitos) != 11:
        return False

    # La serie de multiplicadores estándar del CUIT.
    multiplicadores = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    suma = sum(int(digitos[i]) * multiplicadores[i] for i in range(10))

    resto = suma % 11
    verificador_esperado = 11 - resto
    if verificador_esperado == 11:
        verificador_esperado = 0
    elif verificador_esperado == 10:
        # Caso especial poco común: el CUIT usa otra base. Lo tratamos como inválido
        # para marcarlo a revisar, sin bloquear la carga.
        return False

    return verificador_esperado == int(digitos[10])
