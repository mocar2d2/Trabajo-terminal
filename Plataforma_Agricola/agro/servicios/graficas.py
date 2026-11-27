"""Construccion de figuras Plotly (JSON) a partir de los datos cargados.

Los ejes temporales usan fechas reales (type="date") con formatos de
etiqueta que cambian segun el intervalo visible (tickformatstops): años en la
vista general, meses al acercarse y dias en niveles cercanos. La granularidad
mostrada nunca es mayor que la frecuencia de la serie.

La paleta y los estilos por concepto (observado, ajuste, pronostico) se
definen una sola vez en este modulo. Las semanas sin registros se dejan como
cortes de la linea: solo en la capa de visualizacion se insertan valores
nulos; los datos y los resultados no se modifican.
"""
from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..configuracion import MESES, VARIABLES_CLIMA

# ------------------------------------------------------------------ paleta
# Identidad verde del sitio (--primario y --primario-oscuro en app.css) con
# acentos compatibles; todos los colores de linea tienen contraste >= 3:1 sobre blanco.
VERDE_OSCURO = "#135c3b"
VERDE = "#1f7a50"
VERDE_CLARO = "#4f9d5d"
OLIVA = "#6b7f2a"
OLIVA_CLARO = "#7c8c22"
CARBON = "#3d4441"
GRIS = "#7d858c"
OCRE = "#b7791f"
BRONCE = "#8c6d1f"
TERRACOTA = "#a4492b"
VERDE_AZULADO = "#2f8a80"

SERIES = [VERDE, OCRE, OLIVA, CARBON, TERRACOTA, VERDE_CLARO, VERDE_AZULADO, BRONCE]
# Estilo por concepto: el color se complementa con el tipo de linea.
OBSERVADO = {"color": VERDE_OSCURO, "dash": "solid", "width": 2.2}
AJUSTE_DASH = "dot"
PRONOSTICO_DASH = "dash"
SOMBRA_HUECO = "rgba(125, 133, 140, 0.08)"  # tenue: no compite con los datos

# Clima: temperaturas en tonos calidos; precipitacion en verde (variable humeda).
COLOR_CLIMA = {"tmax": "#b5381f", "tmin": "#c96f1e", "precip": VERDE}
# Sequia: rojizos y anaranjados para la condicion seca (semanas sin precipitacion y
# temperaturas); la precipitacion conserva un tono humedo para no confundirse con ella.
SEQUIA = {"precip": OLIVA, "sin_precip": "#7a1f12", "tmax": "#b5381f", "tmin": "#c96f1e", "umbral": "#6e4a2e"}

TEXTO = "#1f2328"
TEXTO_2 = "#57606a"
REJILLA = "#e6e8eb"
ESCALA_PRECIO = [[0, "#f1f8f3"], [0.25, "#b5dcc2"], [0.5, "#5aa469"], [0.75, "#1f7a50"], [1, "#0d3d25"]]
ESCALA_FALTANTES = [[0, "#ffffff"], [0.25, "#f1e2c0"], [0.5, "#d3a456"], [0.75, "#9a6418"], [1, "#4f330b"]]
# Abreviaturas de los meses con punto abreviativo, en minúscula.
MES_CORTO = ["ene.", "feb.", "mar.", "abr.", "may.", "jun.", "jul.", "ago.", "sept.", "oct.", "nov.", "dic."]

DIA_MS = 86_400_000
# dtick < 1 mes: dia y mes; 1 a 11 meses: mes y año; >= 1 año: solo año.
FORMATOS_FECHA = [
    {"dtickrange": [None, "M1"], "value": "%-d %b<br>%Y"},
    {"dtickrange": ["M1", "M12"], "value": "%b<br>%Y"},
    {"dtickrange": ["M12", None], "value": "%Y"},
]
FORMATO_TOOLTIP = "%-d %b %Y"
# Control de rango bajo el eje temporal: muestra siempre la serie completa (escala propia)
# aunque el eje principal se ajuste al intervalo visible.
def _control_rango(grosor=0.08):
    return {"visible": True, "thickness": grosor, "bgcolor": "#f7f9f8", "bordercolor": REJILLA, "borderwidth": 1,
            "yaxis": {"rangemode": "auto"}}


# Títulos del eje horizontal: cada punto semanal se rotula con la fecha en que termina
# su semana (precios: resample("W"), domingo; clima: W-WED, miércoles).
EJE_SEMANA_DOMINGO = "Fecha de cierre de la semana (domingo)"
EJE_SEMANA_MIERCOLES = "Fecha de cierre de la semana (miércoles)"


def _base(fig, titulo_y="", alto=420, titulo_x=None):
    fig.update_layout(
        template="none",
        colorway=SERIES,
        separators=".,",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"family": "Inter, Segoe UI, Roboto, Arial, sans-serif", "size": 13, "color": TEXTO},
        margin={"l": 56, "r": 16, "t": 24, "b": 48},
        height=alto,
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        hoverlabel={"bgcolor": "#ffffff", "font": {"color": TEXTO}},
    )
    # automargin: el margen crece si un titulo o etiqueta de eje no cabe (pantallas estrechas).
    # exponentformat="none": cifras completas, sin abreviaturas (k, M) ni notacion cientifica.
    comun = {"automargin": True, "color": TEXTO_2, "exponentformat": "none", "separatethousands": True,
             "tickfont": {"size": 12}, "title_font": {"size": 12, "color": TEXTO_2}}
    fig.update_xaxes(showgrid=False, linecolor=REJILLA, tickcolor=REJILLA, **comun)
    fig.update_yaxes(gridcolor=REJILLA, zeroline=False, title_text=titulo_y, **comun)
    if titulo_x:
        fig.update_xaxes(title_text=titulo_x)
    return fig


def _eje_tiempo(fig, revision, ajustar_y=True):
    """Eje de fechas con detalle progresivo al hacer zoom.

    meta.ajustarY indica al navegador que recalcule la escala vertical con los
    datos del intervalo visible cuando cambia el eje temporal.
    """
    fig.update_xaxes(type="date", tickformatstops=FORMATOS_FECHA, hoverformat=FORMATO_TOOLTIP,
                     nticks=8)
    # uirevision conserva el zoom del usuario mientras la seleccion no cambie.
    fig.update_layout(uirevision=revision)
    if ajustar_y:
        meta = dict(fig.layout.meta or {})
        meta["ajustarY"] = True
        fig.update_layout(meta=meta)
    return fig


def a_json(fig) -> dict:
    return json.loads(fig.to_json())


def _fechas(index):
    return [d.strftime("%Y-%m-%d") for d in index]


def _valores(serie):
    return [None if pd.isna(v) else float(v) for v in serie.values]


def _tooltip(etiqueta, formato, unidad):
    return "%{y:" + formato + "} " + unidad + "<extra>" + etiqueta + "</extra>"


def _cortes(fechas, columnas, regla="W-SUN"):
    """Inserta un punto nulo entre dos registros separados por al menos una
    semana completa sin datos, para que la linea no simule continuidad.
    Devuelve (x, {columna: y}). Solo afecta a la representacion."""
    f = pd.to_datetime(pd.Series(list(fechas))).reset_index(drop=True)
    semanas = f.dt.to_period(regla)
    x, ys = [], {k: [] for k in columnas}
    for i in range(len(f)):
        if i and (semanas[i] - semanas[i - 1]).n > 1:
            medio = f[i - 1] + (f[i] - f[i - 1]) / 2
            x.append(medio.strftime("%Y-%m-%d"))
            for k in columnas:
                ys[k].append(None)
        x.append(f[i].strftime("%Y-%m-%d"))
        for k, v in columnas.items():
            v = v[i]
            ys[k].append(None if v is None or pd.isna(v) else float(v))
    return x, ys


def _semanal_completo(df):
    """Reindexa una tabla semanal a todas sus semanas (paso de 7 dias) para que las
    semanas ausentes aparezcan como cortes. Si las fechas no son semanales, no cambia."""
    if df.empty:
        return df
    completo = pd.date_range(df.index.min(), df.index.max(), freq="7D")
    if not df.index.isin(completo).all():
        return df
    return df.reindex(completo)


# Una etiqueta dentro del sombreado solo si el tramo ocupa al menos esta fracción del periodo
# graficado; en tramos angostos no cabe y la nota junto a la gráfica ya lo describe.
FRACCION_ETIQUETA_HUECO = 0.12


def _sombrear(fig, huecos, etiqueta=None, periodo=None):
    """Sombrea, debajo de los datos, los tramos sin registros (desde/hasta son las
    observaciones que los delimitan) en el panel del eje y principal."""
    total = None
    if periodo:
        total = (pd.Timestamp(periodo[1]) - pd.Timestamp(periodo[0])).days or None
    for h in huecos or []:
        fig.add_vrect(x0=h["desde"], x1=h["hasta"], fillcolor=SOMBRA_HUECO, line_width=0, layer="below")
        a, b = pd.Timestamp(h["desde"]), pd.Timestamp(h["hasta"])
        if etiqueta and total and (b - a).days / total >= FRACCION_ETIQUETA_HUECO:
            fig.add_annotation(x=(a + (b - a) / 2).strftime("%Y-%m-%d"), xref="x", y=1, yref="y domain",
                               yanchor="top", yshift=-4, text=etiqueta, showarrow=False,
                               font={"size": 11, "color": TEXTO_2})


def _rango_y(series, x0, x1, incluir_cero=False):
    """Rango vertical con los valores de las series visibles dentro de [x0, x1]."""
    vals = []
    a, b = pd.Timestamp(x0), pd.Timestamp(x1)
    for x, y in series:
        for xi, yi in zip(x, y):
            if yi is not None and a <= pd.Timestamp(xi) <= b:
                vals.append(float(yi))
    if not vals:
        return None
    lo, hi = min(vals), max(vals)
    if incluir_cero:
        lo, hi = min(lo, 0.0), max(hi, 0.0)
    pad = (hi - lo) * 0.06 or max(abs(hi) * 0.05, 1.0)
    return [lo - pad, hi + pad]


# ----------------------------------------------------------------- precios


def figura_precios(sub, unidad, revision="", huecos=None):
    """Cotizaciones registradas. Las semanas sin registros interrumpen la linea."""
    fig = go.Figure()
    grupos = sub.groupby([sub["estado_aux"].fillna("Sin origen"), sub["presentacion"].fillna("")], sort=True)
    solo_uno = grupos.ngroups == 1
    for i, ((estado, pres), g) in enumerate(grupos):
        nombre = estado if not pres else f"{estado} · {pres}"
        color = SERIES[i % len(SERIES)] if not solo_uno else VERDE_OSCURO
        g = g.sort_values("fecha")
        x, ys = _cortes(g["fecha"], {c: g[c].tolist() for c in ("precio_frec", "precio_min", "precio_max")})
        fig.add_trace(go.Scatter(
            x=x, y=ys["precio_frec"], name=f"Precio frecuente · {nombre}",
            mode="lines", line={"width": 2, "color": color}, connectgaps=False,
            hovertemplate=_tooltip(nombre, ".2f", unidad),
        ))
        if solo_uno:
            for col, etiqueta, dash in (("precio_min", "Precio mínimo", "dot"), ("precio_max", "Precio máximo", "dash")):
                if g[col].notna().any():
                    fig.add_trace(go.Scatter(
                        x=x, y=ys[col], name=etiqueta, mode="lines",
                        line={"width": 1.2, "color": GRIS, "dash": dash}, connectgaps=False,
                        hovertemplate=_tooltip(etiqueta, ".2f", unidad),
                    ))
    _base(fig, f"Precio ({unidad})", 460, "Fecha de cotización")
    _eje_tiempo(fig, revision)
    if solo_uno:
        _sombrear(fig, huecos, "Sin cotizaciones", (sub["fecha"].min(), sub["fecha"].max()))
    fig.update_xaxes(rangeslider=_control_rango())
    return fig


def figura_serie_original(resultado, unidad, revision="", huecos=None):
    fig = go.Figure()
    s = pd.DataFrame(resultado["serie"])
    # Con un solo origen su serie coincide con el promedio semanal: no se repite.
    origenes = resultado.get("por_origen", {}) if len(resultado.get("por_origen", {})) > 1 else {}
    for i, (origen, lista) in enumerate(sorted(origenes.items())):
        d = pd.DataFrame(lista)
        fig.add_trace(go.Scatter(
            x=d["fecha"], y=d["valor"], name=f"Origen: {origen}", mode="lines",
            line={"width": 1.2, "color": SERIES[(i + 1) % len(SERIES)]}, opacity=0.75, connectgaps=False,
            hovertemplate=_tooltip(f"Origen: {origen}", ".2f", unidad),
        ))
    fig.add_trace(go.Scatter(
        x=s["fecha"], y=s["valor"], name="Promedio semanal", mode="lines",
        line={"width": OBSERVADO["width"], "color": OBSERVADO["color"]}, connectgaps=False,
        hovertemplate=_tooltip("Promedio semanal", ".2f", unidad),
    ))
    _base(fig, f"Precio ({unidad})", 440, EJE_SEMANA_DOMINGO)
    _eje_tiempo(fig, revision)
    if len(s):
        _sombrear(fig, huecos, "Sin cotizaciones", (s["fecha"].iloc[0], s["fecha"].iloc[-1]))
    fig.update_xaxes(rangeslider=_control_rango())
    return fig


def figura_stl(resultado, unidad, revision=""):
    """STL aditiva sobre el precio (sin logaritmos): observado = tendencia +
    estacionalidad + residuo, todos en la unidad del precio. La estacionalidad y
    el residuo son desviaciones alrededor de cero."""
    d = resultado["descomposicion"]
    filas = [("observado", "Serie semanal con interpolación", f"Precio ({unidad})"),
             ("tendencia", "Tendencia", f"Precio ({unidad})"),
             ("estacionalidad", "Patrón de temporada (ciclo anual)", f"Desviación ({unidad})"),
             ("residuo", "Variaciones restantes", f"Desviación ({unidad})")]
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.07,
                        subplot_titles=[t for _, t, _ in filas])
    colores = [OBSERVADO["color"], VERDE, OLIVA, CARBON]
    for i, (clave, titulo, eje) in enumerate(filas, start=1):
        df = pd.DataFrame(d[clave])
        fig.add_trace(go.Scatter(x=df["fecha"], y=df["valor"], name=titulo, mode="lines",
                                 line={"width": 1.6, "color": colores[i - 1]},
                                 showlegend=False, hovertemplate=_tooltip(titulo, ".2f", unidad)),
                      row=i, col=1)
    _base(fig, "", 820)
    _eje_tiempo(fig, revision)
    for i, (_, _, eje) in enumerate(filas, start=1):
        fig.update_yaxes(title_text=eje, row=i, col=1)
    for i in (3, 4):
        fig.update_yaxes(zeroline=True, zerolinecolor="#9aa4ae", zerolinewidth=1, row=i, col=1)
    fig.update_xaxes(title_text=EJE_SEMANA_DOMINGO, row=4, col=1)
    fig.update_layout(margin={"t": 40})
    fig.update_annotations(font={"size": 13, "color": TEXTO})
    return fig


def figura_faltantes(mapa):
    fig = go.Figure(go.Heatmap(
        z=mapa["valores"], x=[MES_CORTO[m - 1] for m in mapa["meses"]], y=[str(a) for a in mapa["anios"]],
        colorscale=ESCALA_FALTANTES, zmin=0, zmax=1,
        colorbar={"title": {"text": "Semanas sin<br>cotización", "font": {"size": 12}}, "thickness": 12,
                  "tickformat": ".0%", "tickvals": [0, 0.25, 0.5, 0.75, 1]},
        hovertemplate="%{y} %{x}: %{z:.0%} de semanas sin cotización<extra></extra>", xgap=2, ygap=2,
    ))
    _base(fig, "Año", 380, "Mes")
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)", type="category")
    return fig


def figura_caja_mensual(serie, unidad):
    fig = go.Figure()
    for m, nombre in MESES:
        v = serie[serie.index.month == m]
        if len(v):
            fig.add_trace(go.Box(y=v.values, name=MES_CORTO[m - 1], marker_color=VERDE,
                                 line={"width": 1.4, "color": VERDE_OSCURO}, fillcolor="rgba(31,122,80,0.18)",
                                 boxpoints="outliers", showlegend=False,
                                 hovertemplate="%{y:.2f} " + unidad + "<extra>" + nombre.capitalize() + "</extra>"))
    _base(fig, f"Precio semanal ({unidad})", 400, "Mes")
    fig.update_layout(hovermode="closest")
    return fig


def figura_anio_mes(matriz, unidad):
    fig = go.Figure(go.Heatmap(
        z=[[None if pd.isna(v) else float(v) for v in fila] for fila in matriz.values],
        x=[MES_CORTO[int(m) - 1] for m in matriz.columns], y=[str(a) for a in matriz.index],
        colorscale=ESCALA_PRECIO,
        colorbar={"title": {"text": f"Precio<br>({unidad})", "font": {"size": 12}}, "thickness": 12,
                  "tickformat": ",.2f"},
        hovertemplate="%{y} %{x}: %{z:.2f} " + unidad + "<extra></extra>", xgap=2, ygap=2,
    ))
    _base(fig, "Año", 420, "Mes")
    fig.update_layout(hovermode="closest")
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)", type="category")
    return fig


def _barras_periodo(serie, regla, periodo, nombre, color, vista, visible, unidad, formato):
    """Barras agregadas por mes ('MS') o año ('YS') sobre un eje de fechas.

    regla: 'mean' o 'sum' de los valores con dato del periodo.
    """
    s = serie.dropna()
    g = s.groupby(s.index.to_period("M" if periodo == "M1" else "Y"))
    valores = g.mean() if regla == "mean" else g.sum()
    conteo = g.count()
    x = [p.start_time.strftime("%Y-%m-%d") for p in valores.index]
    return go.Bar(
        x=x, y=[float(v) for v in valores.values], customdata=[int(c) for c in conteo.values],
        name=nombre, marker_color=color,
        xperiod=periodo, xperiodalignment="middle", visible=visible, meta={"vista": vista},
        hovertemplate="%{y:" + formato + "} " + unidad + " (%{customdata} semanas con datos)<extra>" + nombre + "</extra>",
    )


def figura_promedios(serie, unidad, revision=""):
    """Promedio anual o mensual de la serie semanal (selector Anual/Mensual)."""
    fig = go.Figure()
    fig.add_trace(_barras_periodo(serie, "mean", "M12", "Promedio anual", VERDE, "anual", True, unidad, ".2f"))
    fig.add_trace(_barras_periodo(serie, "mean", "M1", "Promedio mensual", VERDE, "mensual", False, unidad, ".2f"))
    _base(fig, f"Precio promedio ({unidad})", 360, "Año")
    _eje_tiempo(fig, revision)
    # El navegador cambia el título del eje al alternar Anual/Mensual.
    fig.update_layout(meta={**dict(fig.layout.meta or {}),
                            "textosVista": {"anual": {"xaxis.title.text": "Año"},
                                            "mensual": {"xaxis.title.text": "Mes"}}})
    fig.update_layout(hovermode="closest", bargap=0.25, showlegend=False)
    return fig


# ------------------------------------------------------------------- clima


def figura_clima_estado(semanal, variable, revision=""):
    meta = VARIABLES_CLIMA[variable.upper()]
    col = variable.lower()
    semanal = _semanal_completo(semanal)
    fig = go.Figure()
    if col == "precip":
        fig.add_trace(go.Bar(x=_fechas(semanal.index), y=_valores(semanal[col]), name=meta["etiqueta"],
                             marker_color=COLOR_CLIMA["precip"], xperiod=7 * DIA_MS, xperiodalignment="end",
                             hovertemplate=_tooltip("Acumulada en la semana", ".1f", "mm")))
        titulo = "Precipitación semanal acumulada (mm)"
    else:
        fig.add_trace(go.Scatter(x=_fechas(semanal.index), y=_valores(semanal[col]), name=meta["etiqueta"],
                                 mode="lines+markers", marker={"size": 5},
                                 line={"width": 1.8, "color": COLOR_CLIMA[col]},
                                 connectgaps=False, hovertemplate=_tooltip(meta["etiqueta"], ".1f", "°C")))
        titulo = f"{meta['etiqueta']} semanal promedio (°C)"
    _base(fig, titulo, 360, EJE_SEMANA_MIERCOLES)
    _eje_tiempo(fig, revision)
    if col == "precip":
        fig.update_yaxes(rangemode="tozero")
    fig.update_layout(showlegend=False)
    return fig


PRECIP_VISTA = {"semanal": "Precipitación semanal (mm)", "mensual": "Precipitación mensual (mm)",
                "anual": "Precipitación anual (mm)"}


TRAZOS_UMBRAL = ["dash", "longdash", "dashdot", "longdashdot"]


def figura_sequia(semanal, umbrales, revision=""):
    semanal = _semanal_completo(semanal)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.12,
                        subplot_titles=[PRECIP_VISTA["semanal"],
                                        "Temperatura semanal promedio de las estaciones (°C)"])
    x = _fechas(semanal.index)
    fig.add_trace(go.Bar(x=x, y=_valores(semanal["precip"]), name="Precipitación semanal", marker_color=SEQUIA["precip"],
                         xperiod=7 * DIA_MS, xperiodalignment="end", meta={"vista": "semanal"},
                         hovertemplate=_tooltip("Semanal", ".1f", "mm")), row=1, col=1)
    # Semanas con precipitacion igual a cero (las mismas que cuenta la tabla): una barra de
    # altura cero no se ve, por lo que se marcan sobre el eje.
    secas = semanal.index[semanal["precip"] == 0]
    fig.add_trace(go.Scatter(x=_fechas(secas), y=[0.0] * len(secas), name="Semana sin precipitación",
                             mode="markers", marker={"symbol": "line-ns-open", "size": 9, "color": SEQUIA["sin_precip"],
                                                     "line": {"width": 2, "color": SEQUIA["sin_precip"]}},
                             meta={"vista": "semanal"}, hovertemplate="0 mm<extra>Sin precipitación</extra>"),
                  row=1, col=1)
    fig.add_trace(_barras_periodo(semanal["precip"], "sum", "M1", "Precipitación mensual", SEQUIA["precip"],
                                  "mensual", False, "mm", ".1f"), row=1, col=1)
    fig.add_trace(_barras_periodo(semanal["precip"], "sum", "M12", "Precipitación anual", SEQUIA["precip"],
                                  "anual", False, "mm", ".1f"), row=1, col=1)
    fig.add_trace(go.Scatter(x=x, y=_valores(semanal["tmax"]), name="Temperatura máxima", mode="lines",
                             line={"width": 1.6, "color": SEQUIA["tmax"]}, connectgaps=False,
                             hovertemplate=_tooltip("Máxima", ".1f", "°C")), row=2, col=1)
    fig.add_trace(go.Scatter(x=x, y=_valores(semanal["tmin"]), name="Temperatura mínima", mode="lines",
                             line={"width": 1.6, "color": SEQUIA["tmin"], "dash": "dot"}, connectgaps=False,
                             hovertemplate=_tooltip("Mínima", ".1f", "°C")), row=2, col=1)
    # Umbrales: líneas horizontales identificadas en la leyenda y no con texto sobre el panel,
    # donde las series de temperatura pasan por la misma altura y lo vuelven ilegible.
    # Cada umbral tiene su propio patrón de trazo para distinguirlo en la leyenda.
    if x:
        for i, u in enumerate(umbrales):
            trazo = TRAZOS_UMBRAL[i % len(TRAZOS_UMBRAL)]
            fig.add_trace(go.Scatter(x=[x[0], x[-1]], y=[u["valor"], u["valor"]], name=u["corto"], mode="lines",
                                     line={"color": SEQUIA["umbral"], "dash": trazo, "width": 1.5},
                                     hoverinfo="skip", meta={"umbral": u["clave"]}), row=2, col=1)
    _base(fig, "", 680)
    _eje_tiempo(fig, revision)
    fig.update_yaxes(title_text="Precipitación (mm)", rangemode="tozero", row=1, col=1)
    fig.update_yaxes(title_text="Temperatura (°C)", row=2, col=1)
    # El eje compartido corresponde a la temperatura (siempre semanal); el título del panel
    # de precipitación indica si sus barras son semanales, mensuales o anuales.
    fig.update_xaxes(title_text=EJE_SEMANA_MIERCOLES, row=2, col=1)
    fig.update_layout(meta={**dict(fig.layout.meta or {}),
                            "textosVista": {v: {"annotations[0].text": t} for v, t in PRECIP_VISTA.items()}})
    # Leyenda bajo la gráfica: arriba competiría con el título del primer panel.
    fig.update_layout(margin={"t": 44}, legend={"orientation": "h", "x": 0, "xanchor": "left", "y": -0.12,
                                                "yanchor": "top"})
    fig.update_annotations(font={"size": 12})
    return fig


def figura_comparacion(unido, variable, unidad_precio, producto, estado, revision="", huecos=None,
                       serie_precio=None, clima_semanal=None):
    """Dos paneles verticales con un unico eje temporal real, en el periodo comparado
    (de la primera a la ultima semana con precio y clima).

    Cada panel muestra los valores registrados de su fuente en ese periodo: el precio
    semanal del producto y origen, y la variable climatica del estado (semana climatica
    asignada a la semana de precio que la contiene). Las semanas sin dato quedan vacias:
    no se interpolan ni se unen observaciones separadas. huecos: tramos sin precio.
    """
    meta = VARIABLES_CLIMA[variable.upper()]
    col = variable.lower()
    u = unido.set_index("semana").sort_index()
    semanas = pd.date_range(u.index.min(), u.index.max(), freq="W-SUN")
    if serie_precio is not None:
        precio = serie_precio.reindex(semanas)
    else:
        precio = u["precio"].reindex(semanas)
    if clima_semanal is not None and not clima_semanal.empty:
        c = clima_semanal[col].copy()
        c.index = c.index + pd.Timedelta(days=4)  # misma regla que la union (miercoles -> domingo)
        clima = c.reindex(semanas)
    else:
        clima = u[col].reindex(semanas)
    x = _fechas(semanas)
    etiqueta_precio = f"Precio semanal ({unidad_precio})"
    etiqueta_clima = f"{meta['etiqueta']} semanal ({meta['unidad']})"
    if col == "precip":
        etiqueta_clima = "Precipitación semanal acumulada (mm)"
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=_valores(precio), name=etiqueta_precio, mode="lines+markers",
        line={"width": OBSERVADO["width"], "color": OBSERVADO["color"]}, marker={"size": 4, "color": OBSERVADO["color"]},
        connectgaps=False, xaxis="x", yaxis="y",
        hovertemplate="%{y:,.2f} " + unidad_precio + "<extra>Precio</extra>",
    ))
    if col == "precip":
        fig.add_trace(go.Bar(
            x=x, y=_valores(clima), name=etiqueta_clima, marker_color=COLOR_CLIMA["precip"], xaxis="x", yaxis="y2",
            hovertemplate="%{y:.1f} mm<extra>" + meta["etiqueta"] + "</extra>",
        ))
    else:
        fig.add_trace(go.Scatter(
            x=x, y=_valores(clima), name=etiqueta_clima, mode="lines", connectgaps=False,
            line={"width": 1.8, "color": COLOR_CLIMA[col]}, xaxis="x", yaxis="y2",
            hovertemplate="%{y:.1f} °C<extra>" + meta["etiqueta"] + "</extra>",
        ))
    _base(fig, "", 600)
    _eje_tiempo(fig, revision or f"{producto}-{estado}-{variable}")
    eje_y = {"automargin": True, "gridcolor": REJILLA, "zeroline": False, "color": TEXTO_2,
             "exponentformat": "none", "separatethousands": True, "tickfont": {"size": 12},
             "title": {"font": {"size": 12, "color": TEXTO_2}}}
    clima_titulo = "Precipitación (mm)" if col == "precip" else f"{meta['etiqueta']} (°C)"
    fig.update_layout(
        hovermode="x unified",
        hoversubplots="axis",
        margin={"t": 40},
        yaxis={**eje_y, "domain": [0.56, 1.0], "tickformat": ",.2f",
               "title": {**eje_y["title"], "text": f"Precio ({unidad_precio})"}},
        yaxis2={**eje_y, "domain": [0.0, 0.44], "title": {**eje_y["title"], "text": clima_titulo},
                "rangemode": "tozero" if col == "precip" else "normal"},
        xaxis={"anchor": "y2", "type": "date", "tickformatstops": FORMATOS_FECHA,
               "hoverformat": FORMATO_TOOLTIP, "nticks": 8, "showgrid": False, "linecolor": REJILLA,
               "tickcolor": REJILLA, "color": TEXTO_2, "automargin": True, "showspikes": True, "spikemode": "across", "spikethickness": 1,
               "spikecolor": "#9aa4ae", "spikedash": "dot", "tickfont": {"size": 12},
               "title": {"text": EJE_SEMANA_DOMINGO, "font": {"size": 12, "color": TEXTO_2}}},
    )
    # Sombreado solo en el panel del precio: es el precio el que falta en esos tramos.
    _sombrear(fig, huecos, "Sin registros de precio", (semanas[0], semanas[-1]))
    return fig


# --------------------------------------------------- validacion del pronostico

# Modelos principales; junto con el de menor error forman la seleccion inicial.
VALIDACION_VISIBLES = {"SARIMA (sin clima)", "SARIMAX", "Koyck (Δ)", "STL sin clima", "Ingenuo (último valor)"}
COLORES_VALIDACION = {
    "SARIMA (sin clima)": VERDE_CLARO, "SARIMAX": OCRE, "Koyck (niveles)": BRONCE, "Koyck (Δ)": TERRACOTA,
    "STL sin clima": OLIVA, "STL sin clima (estacional = último ciclo)": VERDE_AZULADO, "STL con clima": OLIVA_CLARO,
    "Ingenuo (último valor)": CARBON, "Ingenuo estacional (52 semanas antes)": GRIS,
}
SEMANAS_CONTEXTO = 13  # semanas del final del entrenamiento visibles junto al año de evaluación


def _nombre_corto(texto):
    """Parte en dos líneas los nombres largos de la leyenda (pantallas estrechas)."""
    return texto.replace(" (", "<br>(", 1) if len(texto) > 30 else texto


def modelos_validacion(prod):
    return [n for n in prod["prueba"]["pronosticos"] if "referencia" not in n]


def seleccion_inicial(prod, mejor):
    """Modelos principales y el de menor error (criterio vigente de la plataforma)."""
    return [n for n in modelos_validacion(prod) if n in VALIDACION_VISIBLES or n == mejor]


def figura_validacion(prod, unidad, revision="", mejor=None, huecos=None):
    """Serie observada (W-WED), valores ajustados en entrenamiento y pronosticos de
    evaluacion de 2025 emitidos al cierre de 2024. Las semanas sin cotizacion real
    se dejan vacias en la serie observada. La vista inicial muestra el año de
    evaluacion; meta.vistas guarda los intervalos para los controles de periodo."""
    fig = go.Figure()
    serie = prod["serie"]
    prueba = prod["prueba"]
    iniciales = set(seleccion_inicial(prod, mejor))
    obs = [v if o else None for v, o in zip(serie["precio"], serie["observado"])]
    fig.add_trace(go.Scatter(
        x=serie["fechas"], y=obs, name="Precio observado", mode="lines+markers",
        line={"width": OBSERVADO["width"], "color": OBSERVADO["color"]}, marker={"size": 3.5, "color": OBSERVADO["color"]},
        connectgaps=False, meta={"rol": "observado"},
        hovertemplate=_tooltip("Precio observado", ".2f", unidad),
    ))
    for nombre, aj in prod.get("ajuste", {}).items():
        fig.add_trace(go.Scatter(
            x=aj["fechas"], y=aj["valores"], name=_nombre_corto(f"Ajuste: {nombre}"), mode="lines",
            line={"width": 1.2, "color": COLORES_VALIDACION.get(nombre, GRIS), "dash": AJUSTE_DASH},
            visible="legendonly", meta={"rol": "ajuste", "modelo": nombre},
            hovertemplate=_tooltip(f"Ajuste {nombre}", ".2f", unidad),
        ))
    visibles = [(serie["fechas"], obs)]
    for nombre in modelos_validacion(prod):
        valores = prueba["pronosticos"][nombre]
        ver = nombre in iniciales
        if ver:
            visibles.append((prueba["fechas"], valores))
        fig.add_trace(go.Scatter(
            x=prueba["fechas"], y=valores,
            name=_nombre_corto(f"Pronóstico: {nombre}" + (" · menor error" if nombre == mejor else "")),
            mode="lines",
            line={"width": 2.4 if nombre == mejor else 1.8, "color": COLORES_VALIDACION.get(nombre, GRIS),
                  "dash": PRONOSTICO_DASH},
            visible=True if ver else "legendonly", meta={"rol": "pronostico", "modelo": nombre},
            hovertemplate=_tooltip(nombre, ".2f", unidad),
        ))
    _base(fig, f"Precio ({unidad})", 660, EJE_SEMANA_MIERCOLES)
    _eje_tiempo(fig, revision)
    # Muchas series: la leyenda va debajo de la gráfica y del control de rango.
    fig.update_layout(legend={"orientation": "h", "x": 0, "xanchor": "left", "y": -0.42, "yanchor": "top",
                              "maxheight": 0.9})
    corte = prueba["fechas"][0]
    fin = prueba["fechas"][-1]
    inicio_eval = (pd.Timestamp(corte) - pd.Timedelta(weeks=SEMANAS_CONTEXTO)).strftime("%Y-%m-%d")
    fin_eval = (pd.Timestamp(fin) + pd.Timedelta(days=4)).strftime("%Y-%m-%d")
    fig.add_vrect(x0=corte, x1=fin, fillcolor="rgba(31,122,80,0.06)", line_width=0, layer="below")
    fig.add_shape(type="line", x0=corte, x1=corte, xref="x", y0=0, y1=1, yref="paper",
                  line={"color": "#9aa4ae", "width": 1, "dash": "dot"})
    fig.add_annotation(x=corte, y=1, xref="x", yref="paper", text=f"{corte[:4]}: evaluación", showarrow=False,
                       xanchor="left", yanchor="top", xshift=4, bgcolor="rgba(255,255,255,0.85)",
                       font={"size": 11, "color": TEXTO_2})
    fig.add_annotation(x=corte, y=1, xref="x", yref="paper", text="Entrenamiento", showarrow=False,
                       xanchor="right", yanchor="top", xshift=-4, bgcolor="rgba(255,255,255,0.85)",
                       font={"size": 11, "color": TEXTO_2})
    _sombrear(fig, huecos)
    vistas = {"evaluacion": [inicio_eval, fin_eval], "historico": [serie["fechas"][0], fin_eval]}
    fig.update_layout(meta={**(fig.layout.meta or {}), "vistas": vistas, "vistaInicial": "evaluacion",
                            "iniciales": sorted(iniciales)})
    fig.update_xaxes(range=vistas["evaluacion"], rangeslider=_control_rango(0.07))
    rango = _rango_y(visibles, *vistas["evaluacion"])
    if rango:
        fig.update_yaxes(range=rango)
    return fig
