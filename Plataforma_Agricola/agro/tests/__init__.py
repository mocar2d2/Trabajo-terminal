"""Pruebas de la plataforma.

Si se define PRUEBAS_LIMITE_SEG, al vencer el plazo se imprime la pila de
todos los hilos y el proceso termina (diagnostico de bloqueos).
"""
import faulthandler
import os
import sys

_limite = os.environ.get("PRUEBAS_LIMITE_SEG")
if _limite and _limite.isdigit():
    faulthandler.dump_traceback_later(int(_limite), exit=True, file=sys.stderr)
