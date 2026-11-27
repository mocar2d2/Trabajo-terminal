"""Importacion validada de los CSV a SQLite y calculo de las series de precios.

Reglas: no se rellenan, corrigen ni eliminan valores. Cada fila del CSV se
importa con su numero de fila original. Las columnas auxiliares se calculan
con correspondencias explicitas documentadas.
"""
from __future__ import annotations

import json
import logging
import math

import pandas as pd
from django.conf import settings
from django.db import transaction

from ..configuracion import PRODUCTO_A_CULTIVO
from ..models import CargaDatos, ClimaRegistro, PrecioRegistro, SerieAnalisis
from . import fuente_original
from .integridad import sha256_archivo
from .validacion import (
    FORMATO_FECHA_CLIMA,
    FORMATO_FECHA_PRECIOS,
    validar_clima,
    validar_precios,
)

log = logging.getLogger("agro")


class ErrorValidacion(Exception):
    def __init__(self, reporte):
        self.reporte = reporte
        super().__init__("; ".join(reporte["errores"]))


def _num(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return float(v)


def _txt(v):
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


def estado_auxiliar(origen, origen_estado):
    """Estado de origen unificado (columna auxiliar).

    En granos el estado esta en 'Origen'; en hortalizas en 'Origen_Estado'.
    'Todos' es un valor de la fuente y se conserva tal cual.
    """
    return _txt(origen_estado) or _txt(origen)


def _guardar_reporte(nombre, reporte):
    settings.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ruta = settings.PROCESSED_DIR / nombre
    ruta.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


def importar_precios(ruta) -> dict:
    df, reporte = validar_precios(ruta, PRODUCTO_A_CULTIVO)
    _guardar_reporte("reporte_validacion_precios.json", reporte)
    if reporte["errores"]:
        raise ErrorValidacion(reporte)
    fechas = pd.to_datetime(df["Fecha"], format=FORMATO_FECHA_PRECIOS, errors="coerce")
    precios = df[["Precio Mín", "Precio Max", "Precio Frec"]].apply(pd.to_numeric, errors="coerce")
    objetos = []
    for i, fila in enumerate(df.itertuples(index=False, name=None)):
        r = dict(zip(df.columns, fila))
        f = fechas.iat[i]
        objetos.append(
            PrecioRegistro(
                fila_origen=i + 2,  # fila 1 = encabezado
                fecha_texto=_txt(r["Fecha"]),
                fecha=None if pd.isna(f) else f.date(),
                origen=_txt(r["Origen"]),
                precio_min=_num(precios.iat[i, 0]),
                precio_max=_num(precios.iat[i, 1]),
                precio_frec=_num(precios.iat[i, 2]),
                producto=r["Producto_Buscado"],
                categoria=r["Categoria"],
                anio=None if pd.isna(r["Año"]) else int(r["Año"]),
                mes=_num(r["Mes"]),
                semana=_num(r["Semana"]),
                presentacion=_txt(r["Presentación"]),
                origen_estado=_txt(r["Origen_Estado"]),
                cultivo_aux=PRODUCTO_A_CULTIVO[r["Producto_Buscado"]],
                estado_aux=estado_auxiliar(r["Origen"], r["Origen_Estado"]),
            )
        )
    with transaction.atomic():
        PrecioRegistro.objects.all().delete()
        PrecioRegistro.objects.bulk_create(objetos, batch_size=2000)
        importadas = PrecioRegistro.objects.count()
        if importadas != len(df):
            raise RuntimeError(f"Filas importadas {importadas} != filas origen {len(df)}")
        CargaDatos.objects.create(
            archivo=ruta.name, tipo="precios", sha256=sha256_archivo(ruta),
            filas_origen=len(df), filas_importadas=importadas, reporte=reporte,
        )
    log.info("Precios importados: %s filas", importadas)
    return reporte


def importar_clima(ruta) -> dict:
    df, reporte = validar_clima(ruta)
    _guardar_reporte("reporte_validacion_clima.json", reporte)
    if reporte["errores"]:
        raise ErrorValidacion(reporte)
    fechas = pd.to_datetime(df["FECHA"], format=FORMATO_FECHA_CLIMA)
    tiene_coord = reporte.get("tiene_coordenadas", False)
    objetos = []
    for i, r in enumerate(df.to_dict("records")):
        objetos.append(
            ClimaRegistro(
                fila_origen=i + 2,
                fecha=fechas.iat[i].date(),
                precip=_num(r["PRECIP"]),
                tmax=_num(r["TMAX"]),
                tmin=_num(r["TMIN"]),
                id_estacion=int(r["ID_Estacion"]),
                estado=str(r["Estado"]),
                latitud=_num(r.get("LATITUD")) if tiene_coord else None,
                longitud=_num(r.get("LONGITUD")) if tiene_coord else None,
            )
        )
    with transaction.atomic():
        ClimaRegistro.objects.all().delete()
        ClimaRegistro.objects.bulk_create(objetos, batch_size=4000)
        importadas = ClimaRegistro.objects.count()
        if importadas != len(df):
            raise RuntimeError(f"Filas importadas {importadas} != filas origen {len(df)}")
        CargaDatos.objects.create(
            archivo=ruta.name, tipo="clima", sha256=sha256_archivo(ruta),
            filas_origen=len(df), filas_importadas=importadas, reporte=reporte,
        )
    log.info("Clima importado: %s filas", importadas)
    return reporte


def _sin_nan(obj):
    """Comprueba que el resultado sea JSON estricto (sin NaN/inf)."""
    json.dumps(obj, allow_nan=False)
    return obj


def calcular_series(ruta_precios) -> dict:
    """Series de las secciones 1 a 4 del cuaderno final para cada producto."""
    sha = fuente_original.sha_fuente()
    df = fuente_original.cargar_precios_csv(ruta_precios)
    productos = [p for p in df["Producto_Buscado"].dropna().unique()]
    resumen = {}
    with transaction.atomic():
        SerieAnalisis.objects.all().delete()
        for producto in productos:
            resultado = fuente_original.resumen_producto(df, producto)
            _sin_nan(resultado)
            SerieAnalisis.objects.create(producto=producto, resultado=resultado, sha256_fuente=sha)
            resumen[producto] = {
                "semanas": len(resultado["serie"]),
                "pct_faltantes": resultado["pct_faltantes"],
                "descomposicion": resultado["descomposicion"] is not None,
                "advertencias": resultado["advertencias"],
            }
        CargaDatos.objects.create(
            archivo=settings.FUENTE_ANALISIS, tipo="analisis", sha256=sha,
            filas_origen=len(df), filas_importadas=len(productos), reporte=resumen,
        )
    _guardar_reporte("resumen_series_originales.json", resumen)
    return resumen


def es_finito(v):
    return v is not None and not (isinstance(v, float) and math.isnan(v))
