"""Verifica que los insumos originales no hayan cambiado (SHA-256)."""
from django.core.management.base import BaseCommand, CommandError

from agro.servicios.integridad import verificar_insumos


class Command(BaseCommand):
    help = "Compara los insumos (data/raw y carpeta original) con los hashes registrados."

    def handle(self, *args, **opts):
        fallas = 0
        for r in verificar_insumos():
            estado_raw = "OK" if r["raw_coincide"] else "DIFERENTE"
            if r["usuario_existe"] is None:
                estado_usuario = "no configurado"
            elif r["usuario_existe"] is False:
                estado_usuario = "no encontrado"
            else:
                estado_usuario = "OK" if r["usuario_coincide"] else "DIFERENTE"
            self.stdout.write(f"{r['archivo']}: data/raw={estado_raw}; original={estado_usuario}; sha256={r['esperado']}")
            if not r["raw_coincide"] or r["usuario_coincide"] is False:
                fallas += 1
        if fallas:
            raise CommandError(f"{fallas} archivo(s) no coinciden con el hash registrado.")
        self.stdout.write(self.style.SUCCESS("Integridad verificada: todos los hashes coinciden."))
