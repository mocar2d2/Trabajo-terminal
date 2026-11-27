from django.conf import settings

from .configuracion import HUECO_MIN_SEMANAS

NAVEGACION = [
    ("agro:inicio", "Inicio"),
    ("agro:precios", "Precios"),
    ("agro:clima", "Clima"),
    ("agro:prediccion", "Series y pronóstico"),
    ("agro:eda", "Análisis por año y mes"),
    ("agro:sequia", "Sequía y temperatura"),
    ("agro:comparar", "Precio y clima"),
    ("agro:metodologia", "Metodología"),
]


def plataforma(request):
    actual = getattr(getattr(request, "resolver_match", None), "view_name", "")
    return {
        "navegacion": [{"url": u, "texto": t, "activo": u == actual} for u, t in NAVEGACION],
        "aviso_actualizacion": settings.AVISO_ACTUALIZACION,
        "hueco_min_semanas": HUECO_MIN_SEMANAS,
        "nombre_plataforma": "Modelo predictivo de precios de productos agrícolas en México",
    }
