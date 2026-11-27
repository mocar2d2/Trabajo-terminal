"""Validacion de los CSV de entrada (sin dependencias de Django).

Las funciones leen los archivos tal como estan, reportan hallazgos y nunca
corrigen valores. Un error impide la importacion; una advertencia se
documenta y se muestra, pero no altera los datos.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

COLUMNAS_PRECIOS = [
    "Fecha", "Origen", "Precio Mín", "Precio Max", "Precio Frec", "Producto_Buscado",
    "Categoria", "Año", "Mes", "Semana", "Presentación", "Origen_Estado",
]
COLUMNAS_CLIMA = ["FECHA", "PRECIP", "TMAX", "TMIN", "ID_Estacion", "Estado"]
COLUMNAS_CLIMA_OPCIONALES = ["LATITUD", "LONGITUD"]

# Formato de fecha del cuaderno final (seccion 1).
FORMATO_FECHA_PRECIOS = "%d/%m/%Y"
FORMATO_FECHA_CLIMA = "%Y-%m-%d"


def _codificacion(ruta) -> dict:
    datos = open(ruta, "rb").read()
    bom = datos.startswith(b"\xef\xbb\xbf")
    try:
        datos.decode("utf-8")
        valido = True
    except UnicodeDecodeError:
        valido = False
    return {"utf8_valido": valido, "bom_utf8": bom}


def leer_precios(ruta) -> pd.DataFrame:
    # Misma lectura que fuente_original.cargar_precios_csv() (cuaderno final).
    return pd.read_csv(ruta)


def leer_clima(ruta) -> pd.DataFrame:
    return pd.read_csv(ruta)


def _nulos(df):
    return {c: int(v) for c, v in df.isna().sum().items()}


def validar_precios(ruta, productos_conocidos: dict) -> tuple[pd.DataFrame, dict]:
    reporte = {"archivo": Path(ruta).name, "errores": [], "advertencias": []}
    reporte["codificacion"] = _codificacion(ruta)
    if not reporte["codificacion"]["utf8_valido"]:
        reporte["errores"].append("El archivo no es UTF-8 válido.")
        return pd.DataFrame(), reporte
    df = leer_precios(ruta)
    reporte["filas"] = int(len(df))
    reporte["columnas"] = list(df.columns)
    faltan = [c for c in COLUMNAS_PRECIOS if c not in df.columns]
    if faltan:
        reporte["errores"].append(f"Faltan columnas: {faltan}")
        return df, reporte

    fecha = pd.to_datetime(df["Fecha"], format=FORMATO_FECHA_PRECIOS, errors="coerce")
    sin_fecha = fecha.isna()
    reporte["filas_sin_fecha"] = int(sin_fecha.sum())
    precios = df[["Precio Mín", "Precio Max", "Precio Frec"]].apply(pd.to_numeric, errors="coerce")
    con_precio_sin_fecha = int((sin_fecha & precios.notna().any(axis=1)).sum())
    reporte["filas_con_precio_sin_fecha"] = con_precio_sin_fecha
    if con_precio_sin_fecha:
        reporte["errores"].append(
            f"{con_precio_sin_fecha} filas tienen precio pero fecha no interpretable con {FORMATO_FECHA_PRECIOS}."
        )
    if sin_fecha.any():
        reporte["advertencias"].append(
            f"{int(sin_fecha.sum())} filas sin fecha ni precio: semanas sin cotización registradas en la fuente."
        )
    reporte["fecha_min"] = str(fecha.min().date()) if fecha.notna().any() else None
    reporte["fecha_max"] = str(fecha.max().date()) if fecha.notna().any() else None

    # Prueba de interpretacion alternativa mes/dia para documentar ambiguedad.
    invertida = pd.to_datetime(df["Fecha"], format="%m/%d/%Y", errors="coerce")
    reporte["fechas_invalidas_si_mes_dia"] = int((invertida.isna() & fecha.notna()).sum())

    productos = df["Producto_Buscado"].value_counts().to_dict()
    reporte["productos"] = {k: int(v) for k, v in productos.items()}
    desconocidos = sorted(set(productos) - set(productos_conocidos))
    if desconocidos:
        reporte["errores"].append(
            f"Productos sin correspondencia de cultivo en agro/configuracion.py: {desconocidos}"
        )
    reporte["categorias"] = {k: int(v) for k, v in df["Categoria"].value_counts().items()}

    # Coherencia de columnas Año/Mes con la fecha.
    validas = fecha.notna()
    reporte["anio_no_coincide"] = int((fecha[validas].dt.year != df.loc[validas, "Año"]).sum())
    mes_ok = validas & df["Mes"].notna()
    reporte["mes_no_coincide"] = int((fecha[mes_ok].dt.month != df.loc[mes_ok, "Mes"]).sum())

    llave = ["Fecha", "Producto_Buscado", "Origen", "Origen_Estado", "Presentación"]
    dup = df[validas].duplicated(subset=llave, keep=False)
    reporte["duplicados_llave"] = int(dup.sum())
    reporte["llave_candidata"] = llave
    if dup.any():
        reporte["advertencias"].append(f"{int(dup.sum())} filas repiten la llave candidata {llave}.")

    inconsist = {}
    for prod, g in df.assign(**{c: precios[c] for c in precios}).groupby("Producto_Buscado"):
        d = {
            "min_mayor_max": int((g["Precio Mín"] > g["Precio Max"]).sum()),
            "frec_mayor_max": int((g["Precio Frec"] > g["Precio Max"]).sum()),
            "frec_menor_min": int((g["Precio Frec"] < g["Precio Mín"]).sum()),
            "precio_min_vacio": int((g["Precio Mín"].isna() & g["Precio Frec"].notna()).sum()),
            "registros_con_precio": int(g["Precio Frec"].notna().sum()),
        }
        inconsist[prod] = d
        if d["frec_mayor_max"] and d["frec_mayor_max"] == d["registros_con_precio"]:
            reporte["advertencias"].append(
                f"{prod}: en el 100 % de los registros 'Precio Frec' es mayor que 'Precio Max' "
                f"y 'Precio Mín' está vacío en {d['precio_min_vacio']} registros. "
                "Posible desplazamiento de columnas en la fuente; se conservan los valores originales."
            )
    reporte["coherencia_precios"] = inconsist
    reporte["nulos"] = _nulos(df)
    reporte["dias_semana_granos"] = {
        int(k): int(v)
        for k, v in fecha[validas & (df["Categoria"] == "granos")].dt.dayofweek.value_counts().items()
    }
    return df, reporte


def validar_clima(ruta) -> tuple[pd.DataFrame, dict]:
    reporte = {"archivo": Path(ruta).name, "errores": [], "advertencias": []}
    reporte["codificacion"] = _codificacion(ruta)
    if not reporte["codificacion"]["utf8_valido"]:
        reporte["errores"].append("El archivo no es UTF-8 válido.")
        return pd.DataFrame(), reporte
    df = leer_clima(ruta)
    reporte["filas"] = int(len(df))
    reporte["columnas"] = list(df.columns)
    faltan = [c for c in COLUMNAS_CLIMA if c not in df.columns]
    if faltan:
        reporte["errores"].append(f"Faltan columnas: {faltan}")
        return df, reporte
    reporte["tiene_coordenadas"] = all(c in df.columns for c in COLUMNAS_CLIMA_OPCIONALES)

    fecha = pd.to_datetime(df["FECHA"], format=FORMATO_FECHA_CLIMA, errors="coerce")
    malas = int(fecha.isna().sum())
    reporte["fechas_invalidas"] = malas
    if malas:
        reporte["errores"].append(f"{malas} fechas no cumplen el formato {FORMATO_FECHA_CLIMA}.")
    reporte["fecha_min"] = str(fecha.min().date()) if fecha.notna().any() else None
    reporte["fecha_max"] = str(fecha.max().date()) if fecha.notna().any() else None
    reporte["dias_semana"] = {int(k): int(v) for k, v in fecha.dt.dayofweek.value_counts().items()}
    reporte["semanas_distintas"] = int(fecha.nunique())

    for col in ["PRECIP", "TMAX", "TMIN"]:
        num = pd.to_numeric(df[col], errors="coerce")
        no_num = int((num.isna() & df[col].notna()).sum())
        if no_num:
            reporte["errores"].append(f"{col}: {no_num} valores no numéricos.")
    estacion_num = pd.to_numeric(df["ID_Estacion"], errors="coerce")
    if estacion_num.isna().any():
        reporte["errores"].append("ID_Estacion contiene valores no numéricos o vacíos.")
    if df["Estado"].isna().any():
        reporte["errores"].append("Estado contiene valores vacíos.")

    dup = df.duplicated(subset=["FECHA", "ID_Estacion"], keep=False)
    reporte["duplicados_fecha_estacion"] = int(dup.sum())
    if dup.any():
        reporte["errores"].append(f"{int(dup.sum())} filas repiten (FECHA, ID_Estacion).")
    multi = df.groupby("ID_Estacion")["Estado"].nunique()
    if (multi > 1).any():
        reporte["errores"].append(f"Estaciones con más de un estado: {list(multi[multi > 1].index)}")

    reporte["estaciones"] = int(df["ID_Estacion"].nunique())
    reporte["estaciones_por_estado"] = {
        k: int(v) for k, v in df.groupby("Estado")["ID_Estacion"].nunique().items()
    }
    reporte["tmin_mayor_tmax"] = int((df["TMIN"] > df["TMAX"]).sum())
    if reporte["tmin_mayor_tmax"]:
        reporte["advertencias"].append(f"{reporte['tmin_mayor_tmax']} filas con TMIN > TMAX.")
    reporte["precip_negativa"] = int((df["PRECIP"] < 0).sum())
    if reporte["precip_negativa"]:
        reporte["advertencias"].append(f"{reporte['precip_negativa']} filas con precipitación negativa.")
    reporte["temperatura_faltante"] = int(df["TMAX"].isna().sum())
    reporte["rangos"] = {
        c: {"min": float(df[c].min()), "max": float(df[c].max())} for c in ["PRECIP", "TMAX", "TMIN"]
    }
    reporte["nulos"] = _nulos(df)
    return df, reporte
