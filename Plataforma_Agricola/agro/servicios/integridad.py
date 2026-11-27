"""Verificacion de integridad (SHA-256) de los insumos originales."""
import hashlib
import json
from pathlib import Path

from django.conf import settings


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def registro_hashes() -> dict:
    with open(settings.REGISTRO_HASHES, encoding="utf-8") as f:
        return json.load(f)["archivos"]


def verificar_insumos(incluir_carpeta_usuario: bool = True) -> list[dict]:
    """Compara cada insumo registrado contra su hash inicial.

    Revisa la copia en data/raw y, si existe, el archivo original en la
    carpeta del usuario (directorio padre del proyecto).
    """
    resultados = []
    for nombre, datos in registro_hashes().items():
        esperado = datos["sha256"]
        raw = settings.RAW_DIR / nombre
        fila = {
            "archivo": nombre,
            "esperado": esperado,
            "raw_existe": raw.exists(),
            "raw_coincide": raw.exists() and sha256_archivo(raw) == esperado,
            "usuario_existe": None,
            "usuario_coincide": None,
        }
        if incluir_carpeta_usuario and settings.INSUMOS_USUARIO_DIR:
            original = Path(settings.INSUMOS_USUARIO_DIR) / nombre
            fila["usuario_existe"] = original.exists()
            if original.exists():
                fila["usuario_coincide"] = sha256_archivo(original) == esperado
        resultados.append(fila)
    return resultados


def hash_registrado(nombre: str) -> str | None:
    return registro_hashes().get(nombre, {}).get("sha256")
