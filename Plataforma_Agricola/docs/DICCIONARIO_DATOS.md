# Diccionario de datos

## Tabla `agro_precioregistro` (una fila por fila del CSV de precios)

| Campo | Origen | Tipo | Descripción |
|---|---|---|---|
| fila_origen | — | entero | Número de línea en el CSV (1 = encabezado). |
| fecha_texto | `Fecha` | texto | Valor original sin interpretar. |
| fecha | `Fecha` | fecha | `dd/mm/aaaa` interpretada; nula si la fuente no tiene fecha. |
| origen | `Origen` | texto | Estado de origen (granos). |
| precio_min | `Precio Mín` | real | Precio mínimo, sin modificar. |
| precio_max | `Precio Max` | real | Precio máximo, sin modificar. |
| precio_frec | `Precio Frec` | real | Precio más frecuente, sin modificar. Variable usada por el cuaderno final. |
| producto | `Producto_Buscado` | texto | Producto SNIIM. |
| categoria | `Categoria` | texto | `granos` u `hortalizas`. |
| anio, mes, semana | `Año`, `Mes`, `Semana` | entero/real | Valores originales. |
| presentacion | `Presentación` | texto | Presentación comercial (hortalizas). |
| origen_estado | `Origen_Estado` | texto | Estado de origen (hortalizas) o `Todos`. |
| cultivo_aux | derivado | texto | Cultivo según `PRODUCTO_A_CULTIVO` (agro/configuracion.py). |
| estado_aux | derivado | texto | `Origen_Estado` si existe; si no, `Origen`. |

## Tabla `agro_climaregistro`

| Campo | Origen | Tipo | Unidad |
|---|---|---|---|
| fila_origen | — | entero | — |
| fecha | `FECHA` | fecha | Cierre de semana (miércoles). |
| precip | `PRECIP` | real | mm (suma semanal). |
| tmax | `TMAX` | real | °C (promedio semanal). |
| tmin | `TMIN` | real | °C (promedio semanal). |
| id_estacion | `ID_Estacion` | entero | Clave SMN. |
| estado | `Estado` | texto | — |
| latitud, longitud | `LATITUD`, `LONGITUD` (opcionales) | real | Grados; vacíos en la versión provisional. |

## Tabla `agro_serieanalisis`
Resultado JSON de `fuente_original.resumen_producto()` (secciones 1 a 4 del cuaderno final) por producto: `serie`, `por_origen`, `pct_faltantes`, `mapa_faltantes`, `descomposicion` (`observado`, `tendencia`, `estacionalidad`, `residuo`), `advertencias`; con el SHA-256 del cuaderno final.

## Tabla `agro_cargadatos`
Bitácora de cada importación: archivo, tipo, SHA-256, filas origen/importadas y reporte de validación.
