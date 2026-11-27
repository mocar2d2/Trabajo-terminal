"""Series de precios de las secciones 1 a 4 de Analisis_Precios_SNIIM_vf.ipynb.

Implementacion de produccion de la logica del cuaderno final: lectura del CSV
(fecha dd/mm/aaaa y precios numericos con errors="coerce"), serie semanal por
estado de origen, serie armonizada cuando hay mas de un estado, matriz de
semanas faltantes y descomposicion STL (periodo 52, robusta, con la
interpolacion lineal que el cuaderno aplica solo para esta descomposicion).

No lee ni ejecuta el cuaderno: su SHA-256 se registra como procedencia y una
prueba automatizada compara estas funciones con las del cuaderno. Las
advertencias que el cuaderno imprime se devuelven como lista.
"""
from __future__ import annotations

import pandas as pd
from django.conf import settings
from statsmodels.tsa.seasonal import STL

from .integridad import hash_registrado, sha256_archivo

COLUMNA_PRECIO = "Precio Frec"
PERIODO_ESTACIONAL = 52
MIN_TRASLAPE = 8
FORMATO_FECHA_CSV = "%d/%m/%Y"


class FuenteAlterada(Exception):
    pass


def ruta_fuente():
    return settings.RAW_DIR / settings.FUENTE_ANALISIS


def sha_fuente() -> str:
    """SHA-256 del cuaderno final; falla si falta o difiere del registrado."""
    ruta = ruta_fuente()
    if not ruta.exists():
        raise FuenteAlterada(f"Falta {settings.FUENTE_ANALISIS}.")
    actual = sha256_archivo(ruta)
    esperado = hash_registrado(settings.FUENTE_ANALISIS)
    if esperado and actual != esperado:
        raise FuenteAlterada(f"{settings.FUENTE_ANALISIS} no coincide con el hash registrado.")
    return actual


def preparar_df(df):
    df = df.copy()
    df["Fecha"] = pd.to_datetime(df["Fecha"], format=FORMATO_FECHA_CSV, errors="coerce")
    for col in ["Precio Mín", "Precio Max", "Precio Frec"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def cargar_precios_csv(ruta):
    return preparar_df(pd.read_csv(ruta))


def serie_semanal_por_origen(df, producto):
    """{estado de origen: serie semanal}, sin promediar entre estados."""
    sub = df[df["Producto_Buscado"] == producto].dropna(subset=["Fecha", COLUMNA_PRECIO, "Origen_Estado"])
    sub = sub[sub["Origen_Estado"] != ""]
    resultado = {}
    for origen, grupo in sub.groupby("Origen_Estado"):
        s = grupo.sort_values("Fecha").set_index("Fecha")[COLUMNA_PRECIO]
        s = s.groupby(level=0).mean()
        resultado[origen] = s.resample("W").mean()
    return resultado


def calcular_serie_armonizada(df, producto, advertencias=None):
    """Combina los estados corrigiendo antes su diferencia de nivel."""
    series = serie_semanal_por_origen(df, producto)
    if len(series) < 2:
        return None
    nombres = list(series)
    referencia = series[nombres[0]]
    desfases = {nombres[0]: 0.0}
    for nombre in nombres[1:]:
        serie = series[nombre]
        traslape = referencia.index.intersection(serie.index)
        traslape = traslape[referencia[traslape].notna() & serie[traslape].notna()]
        if len(traslape) < MIN_TRASLAPE and advertencias is not None:
            advertencias.append(
                f"{producto}: solo {len(traslape)} semanas de traslape entre "
                f"'{nombres[0]}' y '{nombre}'; el desfase puede no ser confiable."
            )
        desfases[nombre] = (serie[traslape] - referencia[traslape]).mean()
    centro = sum(desfases.values()) / len(desfases)
    ajustadas = [series[n] - desfases[n] + centro for n in nombres]
    combinada = pd.concat(ajustadas, axis=1, sort=True).mean(axis=1)
    combinada.name = f"{producto} (armonizada)"
    return combinada


def serie_semanal(df, producto, advertencias=None):
    if "Origen_Estado" in df.columns:
        estados = df.loc[df["Producto_Buscado"] == producto, "Origen_Estado"].dropna().unique()
        estados = [e for e in estados if e not in ("", "Todos")]
        if len(estados) > 1:
            armonizada = calcular_serie_armonizada(df, producto, advertencias)
            if armonizada is not None:
                return armonizada
    sub = df[df["Producto_Buscado"] == producto].dropna(subset=["Fecha", COLUMNA_PRECIO])
    sub = sub.sort_values("Fecha").set_index("Fecha")[COLUMNA_PRECIO]
    return sub.groupby(level=0).mean().resample("W").mean()


def porcentaje_faltantes(semanal):
    return float(100 * semanal.isna().mean())


def matriz_faltantes_mensual(semanal):
    tmp = semanal.isna().astype(int).to_frame("faltante")
    tmp["Año"] = tmp.index.year
    tmp["Mes"] = tmp.index.month
    conteo = tmp.groupby(["Año", "Mes"])["faltante"].sum().unstack("Mes")
    total = tmp.groupby(["Año", "Mes"])["faltante"].size().unstack("Mes")
    return (conteo / total).fillna(0)


def descomponer_estacionalidad(semanal, periodo=PERIODO_ESTACIONAL):
    """STL robusta; None con menos de dos ciclos observados (el cuaderno la omite)."""
    if semanal.dropna().shape[0] < 2 * periodo:
        return None
    completa = semanal.interpolate(limit_direction="both")
    return STL(completa, period=periodo, robust=True).fit()


def serie_a_lista(s):
    return [{"fecha": i.strftime("%Y-%m-%d"), "valor": None if pd.isna(v) else float(v)} for i, v in s.items()]


def matriz_a_dict(fraccion):
    return {
        "anios": [int(a) for a in fraccion.index],
        "meses": [int(m) for m in fraccion.columns],
        "valores": fraccion.values.round(3).tolist(),
    }


def stl_a_dict(resultado):
    return {
        "observado": serie_a_lista(resultado.observed),
        "tendencia": serie_a_lista(resultado.trend),
        "estacionalidad": serie_a_lista(resultado.seasonal),
        "residuo": serie_a_lista(resultado.resid),
    }


def resumen_producto(df, producto):
    advertencias = []
    semanal = serie_semanal(df, producto, advertencias)
    por_origen = serie_semanal_por_origen(df, producto)
    stl = descomponer_estacionalidad(semanal)
    if stl is None:
        advertencias.append(
            f"{producto}: historial insuficiente (se necesitan {2 * PERIODO_ESTACIONAL} "
            "semanas) para la descomposición."
        )
    return {
        "producto": producto,
        "serie": serie_a_lista(semanal),
        "por_origen": {o: serie_a_lista(s) for o, s in por_origen.items()},
        "pct_faltantes": porcentaje_faltantes(semanal),
        "mapa_faltantes": matriz_a_dict(matriz_faltantes_mensual(semanal)),
        "descomposicion": stl_a_dict(stl) if stl is not None else None,
        "advertencias": advertencias,
    }
