"""Valida e importa los insumos y calcula las series de precios del cuaderno final.

Uso:
    python manage.py cargar_datos            # precios, clima y series
    python manage.py cargar_datos --solo-clima
    python manage.py cargar_datos --clima Clima_Municipios_Top50_Semanal_v2.csv --registrar-hash
"""
import json
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from agro.servicios import ingesta
from agro.servicios.integridad import sha256_archivo


class Command(BaseCommand):
    help = "Valida e importa los CSV de data/raw a SQLite y calcula las series de precios."

    def add_arguments(self, parser):
        parser.add_argument("--solo-clima", action="store_true", help="Recarga solo el archivo climático.")
        parser.add_argument("--clima", help="Nombre del archivo climático dentro de data/raw.")
        parser.add_argument("--registrar-hash", action="store_true",
                            help="Registra el hash de un nuevo archivo climático en data/hashes_originales.json.")

    def handle(self, *args, **opts):
        precios = settings.RAW_DIR / settings.PRECIOS_CSV
        clima = settings.RAW_DIR / (opts.get("clima") or settings.CLIMA_CSV)
        for ruta in ([clima] if opts["solo_clima"] else [precios, clima]):
            if not ruta.exists():
                raise CommandError(f"No existe el archivo {ruta}")

        if opts["registrar_hash"]:
            registro = json.loads(settings.REGISTRO_HASHES.read_text(encoding="utf-8"))
            registro["archivos"].setdefault(clima.name, {
                "sha256": sha256_archivo(clima), "bytes": clima.stat().st_size,
                "registrado": date.today().isoformat(),
            })
            settings.REGISTRO_HASHES.write_text(json.dumps(registro, indent=2, ensure_ascii=False), encoding="utf-8")
            self.stdout.write(f"Hash registrado para {clima.name}")

        try:
            if not opts["solo_clima"]:
                r = ingesta.importar_precios(precios)
                self._informe("Precios", r)
            r = ingesta.importar_clima(clima)
            self._informe("Clima", r)
            if not opts["solo_clima"]:
                resumen = ingesta.calcular_series(precios)
                for prod, d in resumen.items():
                    self.stdout.write(
                        f"  Serie {prod}: {d['semanas']} semanas, {d['pct_faltantes']:.2f} % sin dato, "
                        f"descomposición={'sí' if d['descomposicion'] else 'no'}"
                    )
        except ingesta.ErrorValidacion as e:
            raise CommandError(f"Validación fallida: {e}")
        self.stdout.write(self.style.SUCCESS("Carga completada."))

    def _informe(self, nombre, r):
        self.stdout.write(f"{nombre}: {r['filas']} filas leídas de {r['archivo']}")
        for a in r["advertencias"]:
            self.stdout.write(self.style.WARNING(f"  Advertencia: {a}"))
