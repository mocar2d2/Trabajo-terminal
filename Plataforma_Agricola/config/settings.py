"""Configuracion de Django para la plataforma de precios agricolas.

Toda la configuracion sensible proviene de variables de entorno (archivo .env
local no versionado). Por defecto DEBUG es False.
"""
import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .entorno import cargar_env, env_bool, env_lista

BASE_DIR = Path(__file__).resolve().parent.parent
cargar_env(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "Falta DJANGO_SECRET_KEY. Ejecute instalar.ps1 o defina la variable en .env."
    )

DEBUG = env_bool("DJANGO_DEBUG", False)

# Modo de ejecución (lo fija iniciar_plataforma.ps1 en el proceso de Waitress):
# - "publico" (predeterminado): HTTPS a través de ngrok.
# - "local": solo en este equipo, por http://127.0.0.1:PUERTO, sin Internet ni ngrok.
PLATAFORMA_MODO = "local" if os.environ.get("PLATAFORMA_MODO", "").strip().lower() == "local" else "publico"
MODO_LOCAL = PLATAFORMA_MODO == "local"
PUERTO = int(os.environ.get("PUERTO", "8000"))

# Hosts: solo locales y, en modo público, el dominio real de ngrok configurado en .env.
NGROK_DOMINIOS = [] if MODO_LOCAL else [d.replace("https://", "").replace("http://", "").strip("/")
                                        for d in env_lista("NGROK_DOMAIN")]
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "[::1]"] + NGROK_DOMINIOS
CSRF_TRUSTED_ORIGINS = [f"https://{d}" for d in NGROK_DOMINIOS]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "agro.apps.AgroConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "agro.context_processors.plataforma",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "data" / "processed" / "plataforma.sqlite3",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "plataforma-agricola",
        "TIMEOUT": 3600,
    }
}

LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Archivos estaticos (WhiteNoise). El almacenamiento con manifiesto agrega un
# hash al nombre de cada archivo, de modo que los navegadores no reutilizan
# versiones anteriores tras un cambio.
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static_vendor"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# En la suite de pruebas no existe manifiesto de collectstatic.
if "test" in sys.argv[1:2]:
    STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}

# Seguridad para revision mediante ngrok (HTTPS terminado en ngrok).
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = env_bool("COOKIES_SEGURAS", True)
CSRF_COOKIE_SECURE = env_bool("COOKIES_SEGURAS", True)
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
# Los servidores de mosaicos de OpenStreetMap (modo público) exigen el encabezado Referer
# (politica de uso de mosaicos); "same-origin" lo suprimia y provocaba 403.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
# Toda solicitud HTTP se redirige a HTTPS. ngrok envia X-Forwarded-Proto: https;
# los scripts de verificacion local envian el mismo encabezado desde 127.0.0.1
# (Waitress solo lo acepta de esa direccion).
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# No se solicita la lista de precarga de navegadores: el dominio pertenece a
# ngrok y la precarga es un compromiso permanente. check --deploy reporta
# security.W021; es una advertencia aceptada y documentada.
SECURE_HSTS_PRELOAD = False

# Modo local: la aplicación solo escucha en 127.0.0.1 y no hay HTTPS en el equipo,
# por lo que no se redirige a HTTPS, no se envía HSTS y las cookies no exigen HTTPS.
# El modo público conserva la configuración anterior.
if MODO_LOCAL:
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    CSRF_TRUSTED_ORIGINS = [f"http://127.0.0.1:{PUERTO}", f"http://localhost:{PUERTO}"]

# Mapas: en modo público se agrega el fondo de OpenStreetMap; en modo local solo se usa
# la base geográfica incluida en el proyecto (límites estatales), sin solicitudes externas.
MAPA_TESELAS_EXTERNAS = not MODO_LOCAL

# Rutas de datos.
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
REGISTRO_HASHES = BASE_DIR / "data" / "hashes_originales.json"
# Resultados numéricos del modelado de Analisis_Precios_SNIIM_vf.ipynb (calculados fuera de la aplicación).
MODELADO_VF = BASE_DIR / "data" / "derivados" / "modelado_vf.json"
PRECIOS_CSV = os.environ.get("PRECIOS_CSV", "Precios_Historicos_SNIIM_Continuo.csv")
CLIMA_CSV = os.environ.get("CLIMA_CSV", "Clima_Municipios_Top50_Semanal_v1.csv")
# Cuaderno final: procedencia de las series de precios y del modelado.
FUENTE_ANALISIS = "Analisis_Precios_SNIIM_vf.ipynb"
# Carpeta opcional con los insumos originales para compararlos con data/raw.
# Si no se define, la verificacion de integridad usa solo data/raw.
INSUMOS_USUARIO_DIR = os.environ.get("INSUMOS_ORIGINALES_DIR") or None

AVISO_ACTUALIZACION = env_bool("AVISO_ACTUALIZACION", False)

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {
        "archivo": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(LOGS_DIR / "django.log"),
            "maxBytes": 2_000_000,
            "backupCount": 3,
            "encoding": "utf-8",
            "formatter": "simple",
        },
        "consola": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "loggers": {
        "django": {"handlers": ["archivo", "consola"], "level": "WARNING"},
        "agro": {"handlers": ["archivo", "consola"], "level": "INFO"},
    },
}
