# Modelo predictivo de precios de productos agrícolas en México

Aplicación web en Django para consultar precios mayoristas del SNIIM de cinco cultivos (maíz, frijol, haba, tomate y aguacate), variables climáticas semanales del SMN en las regiones productoras y los resultados del modelado de `Analisis_Precios_SNIIM_vf.ipynb` (validación de pronósticos en 2025). La aplicación no entrena modelos: consulta resultados ya calculados.

## Secciones
| Ruta | Contenido |
|---|---|
| `/` | Resumen y último precio por producto |
| `/precios/` | Evolución de precios con filtros por producto, origen, presentación y años; mínimos y máximos |
| `/clima/` | Mapas de temperatura y precipitación (Leaflet) y serie semanal por estado |
| `/prediccion/` | Serie semanal, validación de pronósticos de 2025, descomposición STL y semanas sin cotización |
| `/analisis/` | Distribución mensual, matriz año × mes y promedios anual/mensual |
| `/sequia/` | Precipitación (semanal, mensual, anual) y temperaturas frente a umbrales térmicos |
| `/comparar/` | Precio semanal frente al clima del estado de origen (formulario POST con CSRF) |
| `/metodologia/` | Fuentes y criterios de cálculo |
| `/salud/` | Estado del servicio (JSON mínimo) |

La metodología, las validaciones, los hashes de integridad y las limitaciones están en `docs/METODOLOGIA.md`; los campos y unidades, en `docs/DICCIONARIO_DATOS.md`.

## Dos formas de ejecución
| | Modo local | Modo público |
|---|---|---|
| Comando | `iniciar_plataforma.ps1 -Local` | `iniciar_plataforma.ps1` |
| Dirección | `http://127.0.0.1:8000/` (puerto `PUERTO` de `.env`), solo en este equipo | URL HTTPS de ngrok registrada en `NGROK_DOMAIN` |
| Internet | No se necesita | Necesario (ngrok) |
| Fondo de los mapas | Límites estatales incluidos en el proyecto | OpenStreetMap con el contorno de los estados encima |
| Seguridad | HTTP solo en 127.0.0.1, sin redirección a HTTPS | HTTPS, HSTS, cookies seguras y CSRF con el dominio de ngrok |

Ambos modos usan los mismos archivos estáticos locales (Plotly.js, Leaflet, CSS, JavaScript y la capa geográfica), la misma base de datos y los mismos resultados. `DEBUG` es `False` en los dos. El modo lo fija el script en el proceso de Waitress (`PLATAFORMA_MODO`); no se edita en `.env`.

## A. Uso sin Internet en un equipo ya preparado
Desde la carpeta del proyecto (o indicando la ruta completa de cada script):
```powershell
powershell -ExecutionPolicy Bypass -File .\iniciar_plataforma.ps1 -Local       # inicia y muestra http://127.0.0.1:8000/
powershell -ExecutionPolicy Bypass -File .\verificar_plataforma.ps1 -Local     # comprobaciones del modo local
powershell -ExecutionPolicy Bypass -File .\detener_plataforma.ps1              # detiene la plataforma (cualquier modo)
```
El inicio local no descarga ni instala nada, no inicia ngrok, no recalcula datos ni modelos: aplica migraciones pendientes, prepara los archivos estáticos, ejecuta `check` y la verificación de hashes, e inicia Waitress en 127.0.0.1. Si la plataforma ya está activa en modo local, solo muestra la dirección; si está activa en modo público, indica que se detenga primero. Comprobación manual: desconecte el Wi-Fi, ejecute el inicio local y abra `http://127.0.0.1:8000/` en una ventana privada del navegador.

## B. Publicación con Internet (ngrok)
```powershell
powershell -ExecutionPolicy Bypass -File .\iniciar_plataforma.ps1          # inicia ngrok y Waitress; muestra la URL pública
powershell -ExecutionPolicy Bypass -File .\verificar_plataforma.ps1        # comprobaciones local y pública
powershell -ExecutionPolicy Bypass -File .\detener_plataforma.ps1
```
ngrok se inicia con el dominio registrado en `NGROK_DOMAIN` (si asigna otro, el inicio se detiene sin modificar `.env`). Si no hay Internet o falta el authtoken, el script lo indica y sugiere el modo local. `detener_plataforma.ps1` solo detiene procesos cuyo PID y hora de inicio coinciden con `run/*.json`. La primera visita desde un navegador puede mostrar la página de aviso de ngrok ("Visit Site"); no es un error de la aplicación. Registro: `logs/plataforma.log`.

## C. Instalación inicial en otro equipo (requiere Internet)
Requisitos: Windows 10/11 con PowerShell 5.1 o superior, Python 3.10–3.13 (verificado con 3.12) y, solo para el modo público, ngrok con una cuenta propia.
```powershell
cd "<carpeta del proyecto>"
powershell -ExecutionPolicy Bypass -File .\instalar.ps1
powershell -ExecutionPolicy Bypass -File .\configurar_ngrok.ps1   # solo para el modo público
```
`instalar.ps1` crea `.venv`, descarga e instala `requirements.txt`, genera `.env` con una `DJANGO_SECRET_KEY` aleatoria (no se muestra), verifica hashes, migra, valida e importa los datos, ejecuta `collectstatic`, `check`, `check --deploy` y las pruebas, y marca `data/raw` como solo lectura. `configurar_ngrok.ps1` lee el authtoken del portapapeles sin mostrarlo y lo guarda en la configuración de ngrok del usuario de Windows (fuera del proyecto). Después de esta instalación, el modo local funciona sin Internet. La instalación misma no es offline: necesita PyPI y, para el modo público, ngrok.

Los scripts localizan el proyecto a partir de su propia ubicación (`$PSScriptRoot`) y construyen las rutas con `Join-Path`; no dependen de una carpeta fija ni del directorio desde el que se abre PowerShell.

## Dependencias
- **Aplicación web** (`requirements.txt`): Django 5.2.17, pandas 2.3.3, numpy 2.5.3, statsmodels 0.15.0 (descomposición STL al importar datos), folium 0.20.0, branca 0.8.2, plotly 7.1.0, waitress 3.0.2 y whitenoise 6.12.0.
- **Recursos de la interfaz incluidos en el proyecto**: Leaflet 1.9.4 (`agro/static/agro/vendor/leaflet/`, licencia BSD-2 en `LICENSE.txt`), límites estatales de Natural Earth (`agro/static/agro/geo/`, dominio público, procedencia en `FUENTE.txt`). Plotly.js se copia del paquete `plotly` instalado (`manage.py preparar_estaticos`) a `static_vendor/`; no se usa ningún CDN.
- **Solo para reproducir el cuaderno** (no las necesita la aplicación): Jupyter (`nbclient`/`ipykernel`), matplotlib y scipy. Versiones con las que se reprodujeron los resultados: Python 3.13, pandas 2.3.3, numpy 2.5.3, statsmodels 0.15.0, scipy 1.18.1 y matplotlib 3.11. El cuaderno no se ejecuta al usar la plataforma.

## Insumos, resultados y base de datos
| Ubicación | Contenido |
|---|---|
| `data/raw/` | Insumos originales y vigentes (solo lectura): precios SNIIM, clima v1 (mapas y comparaciones) y v2 (modelado), cierres agrícolas SIAP 2015–2024, `Analisis_Precios_SNIIM_vf.ipynb`, `main-04-11-26.pdf` (reporte final) y `Reporte_Tecnico.pdf` (versión anterior del reporte) |
| `data/hashes_originales.json` | Hashes SHA-256 de los insumos; `manage.py verificar_integridad` los comprueba |
| `data/derivados/modelado_vf.json` | Resultados numéricos del modelado (pronósticos, métricas, parámetros); la aplicación verifica antes los hashes de los insumos usados |
| `data/processed/plataforma.sqlite3` | Base con los datos validados; se reconstruye con `manage.py cargar_datos` si hace falta |

## Pruebas
```powershell
powershell -ExecutionPolicy Bypass -File .\probar.ps1
```
Ejecuta la suite (`manage.py test agro`) con límite de tiempo, `check`, `check --deploy` y la verificación de hashes. Registro: `logs/pruebas.log`.

## Configuración (`.env`)
| Variable | Uso |
|---|---|
| `DJANGO_SECRET_KEY` | Obligatoria; la genera `instalar.ps1` |
| `DJANGO_DEBUG` | `False` |
| `NGROK_DOMAIN` | Dominio público de ngrok (lo registra `iniciar_plataforma.ps1`) |
| `PUERTO` | Puerto local de Waitress (8000) |
| `COOKIES_SEGURAS`, `SECURE_HSTS_SECONDS`, `SECURE_SSL_REDIRECT` | HTTPS en modo público (el modo local los desactiva por sí solo) |
| `AVISO_ACTUALIZACION` | `True` muestra un aviso de mantenimiento |
| `PRECIOS_CSV`, `CLIMA_CSV` | Archivos dentro de `data/raw` |
| `INSUMOS_ORIGINALES_DIR` | Opcional: carpeta con los insumos originales para comparar hashes |

`.env.example` es la plantilla sin secretos. Seguridad: `ALLOWED_HOSTS` explícitos (127.0.0.1, localhost y, en modo público, el dominio de ngrok); Waitress escucha solo en 127.0.0.1 y acepta encabezados de proxy únicamente desde esa dirección. `check --deploy` reporta `security.W021` (precarga HSTS), aceptada porque el dominio pertenece a ngrok.

## Cobertura y limitaciones
- Precios SNIIM: del 2 de enero de 2015 al 31 de diciembre de 2025. La serie semanal rotula cada semana con su domingo de cierre; la última (4 de enero de 2026) solo contiene cotizaciones de diciembre de 2025.
- Clima de mapas, sequía y precio-clima (v1): semanas con cierre del 7 de enero de 2015 al 1 de enero de 2025; el modelado usa los archivos v2 (hasta el 31 de diciembre de 2025), con otra red de estaciones.
- Los pronósticos son una validación fuera de muestra de 2025 (entrenamiento 2015–2024); no hay pronósticos posteriores a diciembre de 2025.
- La descomposición STL de la tendencia del haba no es idéntica a la del reporte en todos los entornos (verosimilitud casi plana); la plataforma muestra los valores reproducidos. Detalle en `docs/METODOLOGIA.md`.
- Las líneas se interrumpen en las semanas sin registros; los tramos de cuatro semanas o más se sombrean y se describen junto a la gráfica.

## Qué entregar y qué excluir al compartir la carpeta
Entregar: código (`agro/`, `config/`, `manage.py`, `servidor.py`), scripts (`*.ps1`, `scripts/`), `requirements.txt`, `.env.example`, `.gitignore`, `README.md`, `docs/` y `data/` completa (`raw`, `derivados`, `processed`, `hashes_originales.json`).

Excluir (propios de este equipo, regenerables o privados):
- `.env`: contiene la clave secreta de Django y el dominio de ngrok.
- `.venv/`: entorno de Python de este equipo; se recrea con `instalar.ps1`.
- `logs/` y `run/`: registros y estado de procesos de las ejecuciones locales.
- `staticfiles/`, `static_vendor/` y carpetas `__pycache__/`: se regeneran al iniciar.

El authtoken de ngrok no se guarda en el proyecto: está en la configuración de ngrok del usuario de Windows.

## Mantenimiento
**Reemplazar el archivo climático.** Copie la nueva versión a `data/raw/` con otro nombre, cambie `CLIMA_CSV` en `.env` y ejecute:
```powershell
.venv\Scripts\python.exe manage.py cargar_datos --solo-clima --registrar-hash
.venv\Scripts\python.exe manage.py test agro
```
Columnas requeridas: `FECHA, PRECIP, TMAX, TMIN, ID_Estacion, Estado`; opcionales `LATITUD, LONGITUD`. Si la validación falla no se modifica la base; el reporte queda en `data/processed/reporte_validacion_clima.json`.

**Nuevo producto.** Agregue su correspondencia en `PRODUCTO_A_CULTIVO` (`agro/configuracion.py`); de lo contrario la carga se detiene.

## Estructura
```
config/                 settings (variables de entorno y modos), urls, wsgi
agro/
  configuracion.py      catálogos, unidades y umbrales centralizados
  models.py             registros de precios, clima, series y bitácora de cargas
  servicios/            validación, ingesta, series del cuaderno, analítica, consultas,
                        figuras Plotly, mapas, resultados del modelado e integridad
  management/commands/  cargar_datos, verificar_integridad, preparar_estaticos
  templates/ static/    interfaz (HTML, CSS, JavaScript, Leaflet y capa geográfica)
  tests/                pruebas automatizadas
data/                   insumos, resultados del modelado, base SQLite y hashes
servidor.py             arranque de Waitress (127.0.0.1)
*.ps1, scripts/         instalación, pruebas, inicio, verificación y detención
```
