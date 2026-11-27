"""Copia plotly.min.js del paquete instalado a static_vendor/ para servirlo localmente."""
import shutil
from pathlib import Path

import plotly
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Prepara archivos estáticos de terceros (Plotly.js) sin depender de CDN."

    def handle(self, *args, **opts):
        origen = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
        if not origen.exists():
            raise CommandError(f"No se encontró {origen}")
        destino = settings.BASE_DIR / "static_vendor" / "vendor"
        destino.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origen, destino / "plotly.min.js")
        self.stdout.write(self.style.SUCCESS(f"Plotly.js {plotly.__version__} preparado."))
