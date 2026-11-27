"""Mapas Folium integrados en plantillas Django (sin iframes).

Se genera el HTML de Folium y se extraen solo el contenedor del mapa y su
script de inicializacion. Leaflet se carga una vez desde la plantilla.
"""
from __future__ import annotations

import html as html_mod
import json
import re

import folium
from branca.colormap import LinearColormap
from django.conf import settings

from ..configuracion import REFERENCIA_ESTADOS, VARIABLES_CLIMA

# Escalas secuenciales: el color mas oscuro corresponde al valor mas alto de la seleccion.
# Temperaturas en tonos calidos (maxima: anaranjado a rojo oscuro; minima: ocre a pardo)
# y precipitacion en verdes, acordes con la paleta de las graficas.
ESCALAS = {
    "TMAX": ["#fff1e6", "#f7b58a", "#eb6834", "#b8461b", "#7a2a0b"],
    "TMIN": ["#fbf6e6", "#ecd59c", "#c9a24a", "#93702a", "#5a4316"],
    "PRECIP": ["#eef7f3", "#a6dcc4", "#4f9d5d", "#1f7a50", "#0d3d25"],
}


def _escala(variable, vmin, vmax):
    if vmin == vmax:
        vmax = vmin + 1e-9
    return LinearColormap(ESCALAS[variable], vmin=vmin, vmax=vmax)


def _fmt(v, unidad):
    return f"{v:.1f} {unidad}"


def _extraer(m):
    completo = m.get_root().render()
    cuerpo = re.search(r"<body>(.*?)</body>", completo, re.S)
    nombre = m.get_name()
    scripts = [s for s in re.findall(r"<script>(.*?)</script>", completo, re.S) if nombre in s]
    return {
        "html": cuerpo.group(1).strip() if cuerpo else "",
        "script": "\n".join(s.strip() for s in scripts),
        "id": nombre,
    }


# Vista del mapa: limites de zoom para que una seleccion pequena no produzca
# un acercamiento excesivo, y nivel regional cuando solo hay un punto.
ZOOM_MIN = 3
ZOOM_MAX = 12
ZOOM_MAX_AJUSTE = 8
ZOOM_UN_PUNTO = 7
PADDING_AJUSTE = (28, 28)


def vista_para_puntos(puntos):
    """Vista que muestra todos los puntos dibujados (coordenadas reales del mapa).

    Varios puntos: limites que los contienen (fitBounds) con relleno y zoom
    maximo. Un punto: centro en esa coordenada con zoom regional.
    """
    if not puntos:
        return None
    lats = [p[0] for p in puntos]
    lons = [p[1] for p in puntos]
    if len(set(zip(lats, lons))) == 1:
        return {"tipo": "centro", "centro": [lats[0], lons[0]], "zoom": ZOOM_UN_PUNTO}
    return {"tipo": "limites", "limites": [[min(lats), min(lons)], [max(lats), max(lons)]],
            "padding": list(PADDING_AJUSTE), "zoomMax": ZOOM_MAX_AJUSTE}


def mapa_clima(por_estado, por_estacion, variable, titulo_periodo, estado=None):
    """Construye el mapa. Devuelve dict con html, script, leyenda y vista.

    Si se indica un estado, solo se dibujan sus puntos y la escala de colores,
    la leyenda y la vista se calculan con esos datos.
    Si hay coordenadas reales de estaciones se dibujan las estaciones; de lo
    contrario se representa el promedio estatal en el punto de referencia del
    estado (no corresponde a la ubicacion de una estacion).
    """
    meta = VARIABLES_CLIMA[variable]
    if estado:
        por_estado = por_estado[por_estado["estado"] == estado]
        por_estacion = por_estacion[por_estacion["estado"] == estado]
    usa_estaciones = (not por_estacion.empty and por_estacion["latitud"].notna().all()
                      and por_estacion["longitud"].notna().all())
    if usa_estaciones:
        valores = por_estacion["valor"]
    elif estado:
        # Un solo punto estatal: la escala abarca el intervalo entre sus estaciones.
        valores = por_estacion["valor"] if not por_estacion.empty else por_estado["valor"]
    else:
        valores = por_estado["valor"]
    vmin, vmax = float(valores.min()), float(valores.max())
    escala = _escala(variable, vmin, vmax)
    sin_referencia = []
    puntos = []
    marcadores = []

    if usa_estaciones:
        for r in por_estacion.itertuples():
            texto = (f"<strong>Estación {r.id_estacion}</strong><br>{html_mod.escape(r.estado)}<br>"
                     f"{meta['etiqueta']}: {_fmt(r.valor, meta['unidad'])}<br>Semanas con datos: {r.semanas}")
            marcadores.append(folium.CircleMarker(
                [r.latitud, r.longitud], radius=7, color="#ffffff", weight=1.5,
                fill=True, fill_color=escala(r.valor)[:7], fill_opacity=0.9, tooltip=folium.Tooltip(texto)))
            puntos.append((float(r.latitud), float(r.longitud)))
    else:
        for r in por_estado.itertuples():
            ref = REFERENCIA_ESTADOS.get(r.estado)
            if ref is None:
                sin_referencia.append(r.estado)
                continue
            texto = (f"<strong>{html_mod.escape(r.estado)}</strong><br>"
                     f"{meta['etiqueta']}: {_fmt(r.valor, meta['unidad'])}<br>"
                     f"Promedio de {r.estaciones} {'estación' if r.estaciones == 1 else 'estaciones'}<br>"
                     f"Intervalo entre estaciones: de {_fmt(r.vmin, meta['unidad'])} a {_fmt(r.vmax, meta['unidad'])}<br>"
                     f"<em>{html_mod.escape(titulo_periodo[:1].upper() + titulo_periodo[1:])}</em>")
            marcadores.append(folium.CircleMarker(
                ref, radius=10 + min(int(r.estaciones), 20) * 0.6, color="#ffffff", weight=2,
                fill=True, fill_color=escala(r.valor)[:7], fill_opacity=0.92, tooltip=folium.Tooltip(texto)))
            puntos.append((float(ref[0]), float(ref[1])))

    vista = vista_para_puntos(puntos)
    centro, zoom = ([23.6, -102.5], 5)
    if vista and vista["tipo"] == "centro":
        centro, zoom = vista["centro"], vista["zoom"]
    # Fondo: OpenStreetMap solo en modo público; la base local de límites estatales
    # (static/agro/geo) la agrega app.js en ambos modos, sin depender de Internet.
    teselas = "OpenStreetMap" if settings.MAPA_TESELAS_EXTERNAS else None
    m = folium.Map(location=centro, zoom_start=zoom, min_zoom=ZOOM_MIN, max_zoom=ZOOM_MAX, tiles=teselas,
                   control_scale=True, width="100%", height="100%", prefer_canvas=True)
    # Solo Leaflet: se omiten Bootstrap/jQuery para no alterar el estilo del sitio.
    m.default_js = []
    m.default_css = []
    for mk in marcadores:
        mk.add_to(m)
    if vista and vista["tipo"] == "limites":
        m.fit_bounds(vista["limites"], padding=PADDING_AJUSTE, max_zoom=ZOOM_MAX_AJUSTE)

    partes = _extraer(m)
    pasos = 5
    leyenda = [
        {"color": escala(vmin + (vmax - vmin) * i / (pasos - 1))[:7],
         "valor": _fmt(vmin + (vmax - vmin) * i / (pasos - 1), meta["unidad"])}
        for i in range(pasos)
    ]
    partes.update({
        "leyenda": leyenda,
        "usa_estaciones": usa_estaciones,
        "sin_referencia": sin_referencia,
        "gradiente": "linear-gradient(90deg," + ",".join(ESCALAS[variable]) + ")",
        "vista": vista,
        "vista_json": json.dumps(vista) if vista else "",
        "puntos": len(puntos),
        "estado": estado,
        "teselas_externas": bool(teselas),
    })
    return partes
