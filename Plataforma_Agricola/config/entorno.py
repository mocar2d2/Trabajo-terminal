"""Lectura minima de variables de entorno desde un archivo .env local.

Las variables ya definidas en el entorno del proceso tienen prioridad sobre
las del archivo. El archivo .env nunca se versiona.
"""
import os
from pathlib import Path


def cargar_env(ruta: Path) -> None:
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8-sig").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave = clave.strip()
        valor = valor.strip().strip('"').strip("'")
        os.environ.setdefault(clave, valor)


def env_bool(nombre: str, defecto: bool = False) -> bool:
    valor = os.environ.get(nombre)
    if valor is None:
        return defecto
    return valor.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


def env_lista(nombre: str) -> list[str]:
    valor = os.environ.get(nombre, "")
    return [v.strip() for v in valor.split(",") if v.strip()]
