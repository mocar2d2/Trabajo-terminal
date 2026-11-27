"""Filtros de presentacion en español (fechas y cifras).

Solo cambian la forma en que se muestran los valores; no los modifican.
"""
from datetime import date, datetime

from django import template

from ..configuracion import MESES, nombre_publico

register = template.Library()
_NOMBRES = dict(MESES)
# Espacio fino de no separación para agrupar cifras de más de cuatro dígitos.
_SEPARADOR_MILES = " "


def _a_fecha(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and len(valor) >= 10:
        try:
            return date.fromisoformat(valor[:10])
        except ValueError:
            return None
    return None


@register.filter
def fecha_larga(valor):
    """2015-01-07 -> 7 de enero de 2015."""
    d = _a_fecha(valor)
    return f"{d.day} de {_NOMBRES[d.month]} de {d.year}" if d else valor


@register.filter
def mes_anio(valor):
    """2015-01-07 -> enero de 2015."""
    d = _a_fecha(valor)
    return f"{_NOMBRES[d.month]} de {d.year}" if d else valor


@register.filter
def cifra(valor):
    """Entero con grupos de tres cifras separados por espacio fino (más de cuatro dígitos)."""
    try:
        n = int(round(float(valor)))
    except (TypeError, ValueError):
        return valor
    texto = str(abs(n))
    if len(texto) > 4:
        grupos = []
        while texto:
            grupos.insert(0, texto[-3:])
            texto = texto[:-3]
        texto = _SEPARADOR_MILES.join(grupos)
    return ("-" if n < 0 else "") + texto


@register.filter
def get_item(diccionario, clave):
    """Valor de un diccionario cuya clave no es un identificador válido (p. ej., «AIC SARIMA»)."""
    try:
        return diccionario.get(clave)
    except AttributeError:
        return None


@register.filter
def producto_publico(valor):
    """Nombre público del producto (p. ej., «Tomate saladette»); el valor interno no cambia."""
    return nombre_publico(valor)
