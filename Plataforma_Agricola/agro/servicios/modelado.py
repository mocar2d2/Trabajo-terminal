"""Resultados del modelado de Analisis_Precios_SNIIM_vf.ipynb (seccion 5).

El notebook se ejecuta fuera de la aplicacion; aqui solo se leen sus resultados
numericos ya calculados (data/derivados/modelado_vf.json). Antes de usarlos se
comprueba que el notebook y los insumos de data/raw tengan el mismo SHA-256
con que se generaron: si no coinciden, no se muestran resultados (no se recurre
a resultados anteriores).
"""
from __future__ import annotations

import json
import threading

from django.conf import settings

from .integridad import sha256_archivo

_lock = threading.Lock()
_cache: dict = {}


class ModeladoNoDisponible(Exception):
    pass


def _verificar(doc):
    for nombre, esperado in doc["fuente"]["insumos"].items():
        ruta = settings.RAW_DIR / nombre
        if not ruta.exists():
            raise ModeladoNoDisponible(f"Falta el insumo {nombre}.")
        if sha256_archivo(ruta) != esperado:
            raise ModeladoNoDisponible(f"{nombre} no coincide con el archivo usado en el modelado.")


def resultados() -> dict:
    """Documento completo, verificado una vez por version del archivo derivado."""
    ruta = settings.MODELADO_VF
    if not ruta.exists():
        raise ModeladoNoDisponible("No existen resultados del modelado.")
    clave = ruta.stat().st_mtime_ns
    with _lock:
        if _cache.get("clave") == clave:
            return _cache["doc"]
    doc = json.loads(ruta.read_text(encoding="utf-8"))
    _verificar(doc)
    with _lock:
        _cache.update({"clave": clave, "doc": doc})
    return doc


def productos_modelados() -> list[str]:
    try:
        return list(resultados()["productos"])
    except ModeladoNoDisponible:
        return []


def producto(nombre) -> dict | None:
    return resultados()["productos"].get(nombre)


# Modelos que se presentan en la validacion (las filas "referencia" usan clima de
# 2025 que no se conocia al emitir el pronostico y se reportan solo en la tabla).
MODELOS_PRINCIPALES = ["SARIMA (sin clima)", "SARIMAX", "Koyck (niveles)", "Koyck (Δ)", "STL sin clima",
                       "STL sin clima (estacional = último ciclo)", "STL con clima",
                       "Ingenuo (último valor)", "Ingenuo estacional (52 semanas antes)"]


def mejor_modelo(prod) -> str | None:
    filas = [m for m in prod["metricas"] if not m["referencia"] and m["rmse"] is not None]
    return min(filas, key=lambda m: m["rmse"])["modelo"] if filas else None
