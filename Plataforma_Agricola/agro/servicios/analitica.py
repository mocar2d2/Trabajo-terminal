"""Calculos derivados reproducibles (sin dependencias de Django).

Todas las funciones reciben DataFrames con los valores originales y devuelven
agregaciones documentadas en docs/METODOLOGIA.md. Ninguna rellena,
interpola ni modifica valores.
"""
from __future__ import annotations

import pandas as pd

# ----------------------------------------------------------------- precios


def filtrar_precios(df, producto=None, estado=None, presentacion=None, anio_desde=None, anio_hasta=None):
    sub = df
    if producto:
        sub = sub[sub["producto"] == producto]
    if estado:
        sub = sub[sub["estado_aux"] == estado]
    if presentacion:
        sub = sub[sub["presentacion"] == presentacion]
    sub = sub[sub["fecha"].notna()]
    if anio_desde:
        sub = sub[sub["fecha"].dt.year >= int(anio_desde)]
    if anio_hasta:
        sub = sub[sub["fecha"].dt.year <= int(anio_hasta)]
    return sub.sort_values("fecha")


def resumen_min_max(sub):
    """Minimos y maximos sobre valores registrados (sin imputacion)."""
    if sub.empty or sub["precio_frec"].notna().sum() == 0:
        return None

    def extremo(col, fn):
        s = sub[sub[col].notna()]
        if s.empty:
            return None
        idx = s[col].idxmin() if fn == "min" else s[col].idxmax()
        fila = s.loc[idx]
        return {"valor": float(fila[col]), "fecha": fila["fecha"].date().isoformat()}

    return {
        "registros": int(sub["precio_frec"].notna().sum()),
        "frec_min": extremo("precio_frec", "min"),
        "frec_max": extremo("precio_frec", "max"),
        "frec_promedio": float(sub["precio_frec"].mean()),
        "precio_min_min": extremo("precio_min", "min"),
        "precio_max_max": extremo("precio_max", "max"),
        "desde": sub["fecha"].min().date().isoformat(),
        "hasta": sub["fecha"].max().date().isoformat(),
    }


def tabla_min_max_por_producto(df, anio=None):
    filas = []
    base = df[df["fecha"].notna()]
    if anio:
        base = base[base["fecha"].dt.year == int(anio)]
    for (cultivo, producto), g in base.groupby(["cultivo_aux", "producto"], sort=False):
        r = resumen_min_max(g)
        if r:
            filas.append({"cultivo": cultivo, "producto": producto, "categoria": g["categoria"].iat[0], **r})
    return filas


def tabla_anual(sub):
    if sub.empty:
        return []
    g = sub.groupby(sub["fecha"].dt.year)
    t = pd.DataFrame({
        "registros": g["precio_frec"].count(),
        "frec_min": g["precio_frec"].min(),
        "frec_max": g["precio_frec"].max(),
        "frec_promedio": g["precio_frec"].mean(),
        "precio_min_min": g["precio_min"].min(),
        "precio_max_max": g["precio_max"].max(),
    })
    t.index.name = "anio"
    t = t.reset_index()
    return [
        {k: (None if pd.isna(v) else (int(v) if k in ("anio", "registros") else float(v))) for k, v in r.items()}
        for r in t.to_dict("records")
    ]


# ------------------------------------------------------------------- series


def serie_original_df(lista):
    """Convierte la lista [{fecha, valor}] de las series de precios a Series."""
    if not lista:
        return pd.Series(dtype=float)
    d = pd.DataFrame(lista)
    s = pd.Series(d["valor"].astype(float).values, index=pd.to_datetime(d["fecha"]))
    return s


def matriz_anio_mes(serie: pd.Series, anio_desde=None, anio_hasta=None):
    """Promedio por año y mes de la serie semanal original (NaN se ignora)."""
    s = serie.dropna()
    if anio_desde:
        s = s[s.index.year >= int(anio_desde)]
    if anio_hasta:
        s = s[s.index.year <= int(anio_hasta)]
    if s.empty:
        return None
    t = s.groupby([s.index.year, s.index.month]).mean().unstack()
    return t


def semanas_en_cobertura(serie: pd.Series, fin_fuente) -> pd.Series:
    """Fecha de referencia de cada semana para agrupar por año y mes.

    La serie semanal del cuaderno rotula cada semana con su domingo de cierre
    (resample("W")). Si ese domingo es posterior a la última fecha del archivo de
    precios, la semana solo contiene cotizaciones anteriores (por ejemplo, la
    semana con cierre el 4 de enero de 2026 reúne cotizaciones del 29 al 31 de
    diciembre de 2025); su fecha de referencia pasa a ser la última fecha del
    archivo, para no crear un año o un mes sin cotizaciones. Las demás semanas
    no cambian y los valores no se modifican.
    """
    if serie.empty or fin_fuente is None or pd.isna(fin_fuente):
        return serie
    fin = pd.Timestamp(fin_fuente)
    indice = serie.index.where(serie.index <= fin, fin)
    return pd.Series(serie.values, index=pd.DatetimeIndex(indice), name=serie.name)


def valores_por_mes(serie: pd.Series, anio_desde=None, anio_hasta=None):
    s = serie.dropna()
    if anio_desde:
        s = s[s.index.year >= int(anio_desde)]
    if anio_hasta:
        s = s[s.index.year <= int(anio_hasta)]
    return s


# ------------------------------------------------------- discontinuidades


def intervalos_sin_observaciones(fechas, regla="W-SUN", minimo=1):
    """Intervalos entre observaciones consecutivas separados por al menos
    `minimo` semanas completas sin registros (semanas de calendario `regla`).

    Solo describe los datos: no rellena ni interpola. Devuelve una lista de
    dicts con la ultima observacion previa (desde), la siguiente (hasta) y el
    numero de semanas sin registros entre ambas.
    """
    f = pd.DatetimeIndex(pd.to_datetime(pd.Series(list(fechas))).dropna().unique()).sort_values()
    if len(f) < 2:
        return []
    semanas = f.to_period(regla)
    salida = []
    for a, b, pa, pb in zip(f[:-1], f[1:], semanas[:-1], semanas[1:]):
        vacias = (pb - pa).n - 1
        if vacias >= minimo:
            salida.append({"desde": a.date().isoformat(), "hasta": b.date().isoformat(), "semanas": int(vacias)})
    return salida


def fechas_observadas(lista):
    """Fechas con valor de una lista [{fecha, valor}]."""
    return [p["fecha"] for p in lista if p["valor"] is not None]


# -------------------------------------------------------------------- clima


def clima_mensual_por_estacion(df, variable, anio, mes=None, estado=None):
    """Agregado mensual (o anual si mes es None) por estacion.

    Semanas asignadas al mes de su fecha de cierre (FECHA). Temperaturas:
    promedio de las semanas con dato. Precipitacion: suma de las semanas con
    dato. Se reporta el numero de semanas con dato.
    """
    sub = df[df["fecha"].dt.year == int(anio)]
    if mes:
        sub = sub[sub["fecha"].dt.month == int(mes)]
    if estado:
        sub = sub[sub["estado"] == estado]
    sub = sub[sub[variable].notna()]
    if sub.empty:
        return pd.DataFrame()
    fn = "sum" if variable == "precip" else "mean"
    g = sub.groupby(["id_estacion", "estado"]).agg(
        valor=(variable, fn), semanas=(variable, "count"),
        latitud=("latitud", "first"), longitud=("longitud", "first"),
    ).reset_index()
    return g


def clima_por_estado(por_estacion):
    """Promedio simple de las estaciones de cada estado."""
    if por_estacion.empty:
        return pd.DataFrame()
    g = por_estacion.groupby("estado").agg(
        valor=("valor", "mean"), estaciones=("id_estacion", "nunique"),
        vmin=("valor", "min"), vmax=("valor", "max"),
    ).reset_index().sort_values("estado")
    return g


def clima_semanal_estado(df, estado, anio_desde=None, anio_hasta=None):
    """Serie semanal del estado: promedio simple de estaciones con dato."""
    sub = df[df["estado"] == estado]
    if anio_desde:
        sub = sub[sub["fecha"].dt.year >= int(anio_desde)]
    if anio_hasta:
        sub = sub[sub["fecha"].dt.year <= int(anio_hasta)]
    if sub.empty:
        return pd.DataFrame()
    g = sub.groupby("fecha").agg(
        precip=("precip", "mean"), tmax=("tmax", "mean"), tmin=("tmin", "mean"),
        estaciones=("id_estacion", "nunique"),
        estaciones_temp=("tmax", "count"),
    ).sort_index()
    return g


def conteo_umbrales(semanal, umbrales, cumple):
    """Semanas por año en que el promedio estatal cumple cada umbral."""
    if semanal.empty:
        return []
    filas = []
    for anio, g in semanal.groupby(semanal.index.year):
        fila = {"anio": int(anio), "semanas": int(len(g)), "celdas": []}
        for u in umbrales:
            col = u["variable"].lower()
            valores = g[col].dropna()
            fila[u["clave"]] = int(sum(cumple(float(v), u) for v in valores))
            fila[u["clave"] + "_con_dato"] = int(len(valores))
            fila["celdas"].append({"conteo": fila[u["clave"]], "con_dato": int(len(valores))})
        fila["sin_precip"] = int((g["precip"] == 0).sum())
        fila["precip_total"] = float(g["precip"].sum())
        filas.append(fila)
    return filas


# ------------------------------------------------- comparacion precio-clima


def semana_precio_de_fecha_clima(fecha_clima: pd.Series) -> pd.Series:
    """Asigna cada semana climatica (cierre miercoles, W-WED) a la semana de
    precios del cuaderno final (resample('W'), cierre domingo) que contiene
    ese miercoles: domingo siguiente = miercoles + 4 dias. La semana climatica
    termina antes del cierre de la semana de precio, por lo que no hay
    informacion futura en la alineacion.
    """
    return fecha_clima + pd.Timedelta(days=4)


def serie_precio_semanal_por_estado(precios, producto, estado):
    """Misma regla del cuaderno final (promedio diario y resample('W'))
    aplicada a un estado de origen (columna auxiliar estado_aux)."""
    sub = precios[(precios["producto"] == producto) & (precios["estado_aux"] == estado)]
    sub = sub.dropna(subset=["fecha", "precio_frec"])
    if sub.empty:
        return pd.Series(dtype=float)
    s = sub.sort_values("fecha").set_index("fecha")["precio_frec"]
    return s.groupby(level=0).mean().resample("W").mean()


def unir_precio_clima(serie_precio: pd.Series, clima_estado: pd.DataFrame):
    """Union 1:1 explicita por semana. Devuelve (df_unido, reporte)."""
    reporte = {"filas_precio": int(serie_precio.notna().sum()), "filas_clima": int(len(clima_estado))}
    if serie_precio.empty or clima_estado.empty:
        reporte.update({"emparejadas": 0, "precio_sin_clima": reporte["filas_precio"],
                        "clima_sin_precio": reporte["filas_clima"], "valida": True})
        return pd.DataFrame(), reporte
    p = serie_precio.dropna().rename("precio").to_frame()
    p.index.name = "semana"
    c = clima_estado.copy()
    c["semana"] = semana_precio_de_fecha_clima(pd.Series(c.index, index=c.index)).values
    c = c.reset_index().rename(columns={"fecha": "fecha_clima"})
    if c["semana"].duplicated().any() or p.index.duplicated().any():
        raise ValueError("Llave de semana duplicada: la union no es 1:1.")
    unido = p.reset_index().merge(c, on="semana", how="inner", validate="one_to_one")
    reporte.update({
        "emparejadas": int(len(unido)),
        "precio_sin_clima": int(len(p) - len(unido)),
        "clima_sin_precio": int(len(c) - len(unido)),
        "valida": len(unido) <= min(len(p), len(c)),
    })
    return unido.sort_values("semana"), reporte


def resumen_comparacion(unido: pd.DataFrame, variable: str) -> dict:
    """Precio de las semanas efectivamente comparadas (union 1:1 precio-clima).

    No se usan semanas fuera del periodo comun ni de otro producto u origen:
    todos los valores provienen de las filas de la union.
    """
    if unido.empty:
        return {}
    u = unido.sort_values("semana")
    col = variable.lower()
    ultima = u.iloc[-1]
    i_min, i_max = u["precio"].idxmin(), u["precio"].idxmax()
    clima_ultima = ultima[col]
    return {
        "desde": u["semana"].iat[0].date(),
        "hasta": ultima["semana"].date(),
        "semanas": int(len(u)),
        "precio_reciente": float(ultima["precio"]),
        "fecha_reciente": ultima["semana"].date(),
        "clima_reciente": None if pd.isna(clima_ultima) else float(clima_ultima),
        "precio_min": float(u.at[i_min, "precio"]),
        "fecha_min": u.at[i_min, "semana"].date(),
        "precio_max": float(u.at[i_max, "precio"]),
        "fecha_max": u.at[i_max, "semana"].date(),
        "precio_promedio": float(u["precio"].mean()),
    }


def presentaciones_comparadas(precios, producto, estado, semanas) -> list[str]:
    """Presentaciones cotizadas en las semanas comparadas (para la unidad del precio)."""
    if len(semanas) == 0:
        return []
    sub = precios[(precios["producto"] == producto) & (precios["estado_aux"] == estado)]
    sub = sub.dropna(subset=["fecha", "precio_frec"])
    # Etiqueta semanal identica a resample("W"): domingo de cierre.
    cierre = sub["fecha"].dt.to_period("W-SUN").dt.end_time.dt.normalize()
    sub = sub[cierre.isin(pd.DatetimeIndex(semanas))]
    return sorted(sub["presentacion"].dropna().unique().tolist())
