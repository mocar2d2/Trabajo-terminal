# Metodología técnica

Documento de referencia para reproducir los resultados de la plataforma: insumos, validaciones, transformaciones, uniones, granularidades, umbrales, discrepancias y limitaciones.

## 1. Insumos e integridad

Los insumos se conservan sin cambios en `data/raw/` (solo lectura). Su hash SHA-256 está registrado en `data/hashes_originales.json` y se verifica con `python manage.py verificar_integridad`, que compara la copia de `data/raw` y, si se define `INSUMOS_ORIGINALES_DIR`, los archivos originales de esa carpeta. La instalación, `probar.ps1` e `iniciar_plataforma.ps1` ejecutan esta verificación.

| Archivo | Bytes | SHA-256 |
|---|---:|---|
| Clima_Municipios_Top50_Semanal_v1.csv | 1,648,068 | `10cc11aee85844b6ca6b0538a769b1d65a34a37f9e2e7f705e2dbe4791b6e3db` |
| Precios_Historicos_SNIIM_Continuo.csv | 989,979 | `86e23cd731750254fe119c449fed78085f316e8876a268541150271169db8589` |
| Analisis_Precios_SNIIM_vf.ipynb (análisis final) | 5,805,177 | `4558bae4c84ced4f29ba764b1614a00e5ad192d7480055a68335cc397a7ecea6` |
| main-04-11-26.pdf (reporte final) | 7,700,803 | `7cee44a27530c657833b89ac7583523cb412e25e43590531e4012268a71f0ec3` |
| Reporte_Tecnico.pdf (versión anterior del reporte) | 2,331,151 | `3f7334f6955085aa014d14cc92e2c81954687ffd81549fdab6cf66561ca19b1a` |

Los insumos del modelado (`Cierre_agricola_mun_2015.csv` a `Cierre_agricola_mun_2024.csv`, `Clima_Municipios_Top50_Semanal_v2.csv`, `Asignacion_Espacial_Validada_k5_v2.csv`, `Clima_Hortalizas_Top50_Semanal_v2.csv` y `Asignacion_Hortalizas_k5_v2.csv`) también están registrados en `data/hashes_originales.json`.

`Analisis_Precios_SNIIM_vf.ipynb` es la referencia metodológica y ejecutable. Las series de precios de sus secciones 1 a 4 (lectura, serie semanal, armonización entre estados, faltantes y STL) están implementadas en `agro/servicios/fuente_original.py`; la aplicación no ejecuta el cuaderno, registra su SHA-256 como procedencia de cada serie y una prueba automatizada compara esas funciones con las del cuaderno, que solo se lee. Los resultados del modelado (sección 5) se leen de `data/derivados/modelado_vf.json`.

## 2. Validación de datos

La validación (`agro/servicios/validacion.py`) se ejecuta en cada carga. Un error detiene la importación sin modificar la base; las advertencias se registran en `data/processed/reporte_validacion_*.json`.

### 2.1 Precios_Historicos_SNIIM_Continuo.csv

| Aspecto | Hallazgo |
|---|---|
| Codificación / separador | UTF-8 con BOM, separador coma. |
| Filas / columnas | 11,447 filas; 12 columnas: `Fecha, Origen, Precio Mín, Precio Max, Precio Frec, Producto_Buscado, Categoria, Año, Mes, Semana, Presentación, Origen_Estado`. |
| Formato de fecha | `dd/mm/aaaa` (el usado por el cuaderno final al leer el CSV). Rango 2015-01-02 a 2025-12-31. |
| Confirmación del formato | Con `dd/mm` todos los registros de granos caen en miércoles (2,131) o martes (44). Interpretadas como `mm/dd`, 6,625 fechas son inválidas y el resto cae en días aleatorios. |
| Filas sin fecha | 636 filas sin fecha ni precio: semanas sin cotización insertadas por el proceso de extracción (Frijol Negro 438, Maíz blanco pozolero 144, Maíz blanco 18, Frijol Pinto 18, Haba 18). Ninguna fila tiene precio sin fecha. |
| Productos (7) / cultivos (5) | Maíz (Maíz blanco 570, Maíz blanco pozolero 565), Frijol (Frijol Pinto 573, Frijol Negro 529), Haba 574, Tomate (Tomate Saladette - Primera 5,946), Aguacate (Aguacate Hass - Primera 2,690). |
| Categorías | `granos` 2,811 filas (frecuencia semanal, miércoles); `hortalizas` 8,636 filas (frecuencia diaria, lunes a viernes). |
| Ubicación | Granos: estado en `Origen` (Puebla, Chihuahua, Sinaloa, México, Veracruz, Zacatecas); `Origen_Estado` vacío. Hortalizas: estado en `Origen_Estado` (Sinaloa, Puebla, `Todos`); `Origen` vacío. |
| Presentación | Solo hortalizas: cajas de 9, 10, 12, 13, 25 y 30 kg. |
| `Año`, `Mes`, `Semana` | `Año` coincide con la fecha en el 100 % de filas con fecha. `Mes` y `Semana` solo existen para granos y `Mes` coincide con la fecha. |
| Duplicados | 0 duplicados en la llave candidata (`Fecha, Producto_Buscado, Origen, Origen_Estado, Presentación`). |
| Unidades | El reporte final (`main-04-11-26.pdf`) documenta MXN/kg para los cinco productos; la presentación de las hortalizas (tamaño de caja) es descriptiva. |
| Coherencia de precios | Mín ≤ Max en todos los registros. **Aguacate Hass**: `Precio Mín` vacío en 2,690/2,690 registros y `Precio Frec` > `Precio Max` en el 100 %. Indica un posible desplazamiento de columnas en la fuente. No se corrige; se muestra advertencia. |

Valores nulos por columna: Fecha 636, Origen 9,272, Precio Mín 3,326, Precio Max 636, Precio Frec 636, Mes 8,636, Semana 8,636, Presentación 2,811, Origen_Estado 2,811.

### 2.2 Clima_Municipios_Top50_Semanal_v1.csv (versión v1)

| Aspecto | Hallazgo |
|---|---|
| Codificación / separador | ASCII (compatible UTF-8), coma. |
| Filas / columnas | 39,951 filas; `FECHA, PRECIP, TMAX, TMIN, ID_Estacion, Estado`. |
| Fechas | ISO `aaaa-mm-dd`, todas en miércoles (semana `W-WED`). 522 semanas, 2015-01-07 a 2025-01-01. |
| Estaciones / estados | 83 estaciones en 15 estados (Jalisco 21, Zacatecas 10, Sinaloa 9, Guanajuato 9, Chihuahua 4, Durango 4, Tamaulipas 4, Campeche 3, Chiapas 3, Guerrero 3, Puebla 3, Sonora 3, Veracruz 3, Nayarit 2, Tlaxcala 2). Cada estación pertenece a un solo estado. |
| Ausencias estructurales | No hay columnas de municipio, coordenadas ni cultivo. El reporte técnico menciona 123 municipios; la versión v1 del archivo contiene 83 estaciones. |
| Duplicados | 0 en (`FECHA`, `ID_Estacion`). |
| Nulos | TMAX y TMIN vacíos en 5,286 filas (mismas filas); PRECIP sin vacíos. 4,820 de esas filas tienen PRECIP = 0. |
| Rangos | PRECIP 0–785 mm/semana (32 semanas > 300 mm); TMAX 7.29–47.5 °C; TMIN −7.43–30 °C; TMIN ≤ TMAX en todas las filas. |
| Unidades | mm y °C (reporte técnico: precipitación sumada y temperaturas promediadas por semana). |

### 2.3 Series de precios del cuaderno final (secciones 1 a 4)

| Aspecto | Hallazgo |
|---|---|
| Sintaxis | Válida (sin magias `%`, comandos `!`, `display()` ni dependencias de estado de celdas). |
| Dependencias | pandas, statsmodels (`STL`). |
| Escritura de archivos | Ninguna. |
| Entradas | CSV de precios (`cargar_precios_csv`). |
| Procesamiento | Promedio diario del `Precio Frec`, `resample("W")` (cierre en domingo); armonización entre estados de origen (`Origen_Estado`) mediante desfase medio; porcentaje y matriz de faltantes; STL (periodo 52, robusto) sobre la serie interpolada linealmente. |
| Salidas | `fuente_original.resumen_producto()` → serie, series por origen, % faltantes, mapa de faltantes, descomposición STL, advertencias. |
| Pronóstico | **No contiene modelo predictivo, pronósticos ni intervalos.** El reporte técnico describe SARIMAX como caso piloto preliminar para haba y no aporta valores numéricos de pronóstico ni archivo serializado. |

Resultado por producto:

| Producto | Semanas | % sin dato | Advertencias |
|---|---:|---:|---|
| Maíz blanco | 574 | 3.83 | — |
| Maíz blanco pozolero | 437 | 3.66 | — |
| Frijol Pinto | 574 | 3.31 | — |
| Frijol Negro | 92 | 1.09 | historial insuficiente para STL |
| Haba | 574 | 3.14 | — |
| Aguacate Hass - Primera | 575 | 2.61 | — |
| Tomate Saladette - Primera | 575 | 2.61 | — |

Tomate: armonización Puebla (referencia) – Sinaloa con 350 semanas de traslape; desfase medio −6.55.

### 2.4 Correspondencia entre archivos

| Unión | Llave | Resultado |
|---|---|---|
| Cuaderno (secciones 1 a 4) ↔ precios | Nombres de columna exactos | Coinciden las 12 columnas usadas. |
| Cuaderno (secciones 1 a 4) ↔ clima | — | Estas secciones no usan clima; el modelado (sección 5) usa los archivos de clima v2 ponderados por producción. |
| Precios ↔ clima | Estado (`estado_aux` ↔ `Estado`, igualdad exacta) + semana | Estados comunes: Sinaloa, Puebla, Chihuahua, Zacatecas, Veracruz. Sin clima: México (Maíz blanco 2015, Maíz blanco pozolero) y `Todos` (Aguacate). No se fuerzan alias. |
| Regla temporal | Semana climática (cierre miércoles) → semana de precio (cierre domingo) que la contiene: `fecha_clima + 4 días` | Unión 1:1 validada (`validate="one_to_one"`); el clima siempre cierra antes que la semana de precio (sin fuga de información futura). |
| Agregación espacial | Promedio simple de estaciones del estado | Documentada; no hay cultivo por estación, por lo que no se asocian estaciones a cultivos. |

Ejemplos verificados: Haba–Puebla 556 semanas con precio, 522 con clima, 504 emparejadas. Tomate–Sinaloa 377/522/327.

### 2.5 Lectura de fechas y crecimiento aparente de precios

- No existe ningún registro anterior a 2015 en ninguno de los archivos; no hay fechas del año 2000.
- Con el formato declarado (`dd/mm/aaaa`) las fechas son coherentes. Si se interpretan sin formato explícito (inferencia `mm/dd`), 7,261 filas se vuelven nulas y las restantes cambian de mes: un tablero que no fije el formato muestra saltos y crecimientos aparentes. **Causa atribuible al software de lectura, no a los datos.** La plataforma usa el formato del cuaderno final y una prueba automatizada lo verifica.
- En los datos originales sí existe un aumento real en 2020: Aguacate Hass pasa de 35.5 (feb) a 47.1 (mar), 51.5 (abr) y 58.8 (may) en promedio mensual de la serie semanal; Frijol Pinto y Haba suben de forma moderada. Junio de 2020 no tiene cotizaciones para ningún producto (hueco de la fuente). Se representa tal cual.
- Tomate: la serie armonizada del cuaderno final baja en abril de 2020 (12.9) frente a meses vecinos (~23), efecto de la armonización cuando solo un origen tiene datos. Se conserva por ser lógica original.

## 3. Transformaciones y trazabilidad

| # | Transformación | Entrada | Salida | Regla | Código |
|---|---|---|---|---|---|
| T1 | Copia de insumos | Carpeta del usuario | `data/raw` | Copia binaria; SHA-256 idéntico; solo lectura. | — |
| T2 | Importación de precios | CSV precios | `agro_precioregistro` | Una fila por fila; `pd.read_csv` igual que el cuaderno final; fecha `%d/%m/%Y` y numéricos con `errors="coerce"` (igual que `preparar_df`). Se conserva `fecha_texto`. | `servicios/ingesta.py` |
| T3 | Columna `cultivo_aux` | `Producto_Buscado` | auxiliar | Diccionario explícito `PRODUCTO_A_CULTIVO`; un producto no mapeado detiene la carga. | `configuracion.py` |
| T4 | Columna `estado_aux` | `Origen`, `Origen_Estado` | auxiliar | `Origen_Estado` si no es nulo; si no, `Origen`. Sin normalización de texto (coincidencias exactas). | `ingesta.estado_auxiliar` |
| T5 | Importación de clima | CSV clima | `agro_climaregistro` | Una fila por fila; fecha `%Y-%m-%d`; errores de formato o duplicados detienen la carga. | `servicios/ingesta.py` |
| T6 | Series del cuaderno final (secciones 1 a 4) | CSV precios | `agro_serieanalisis` | `resumen_producto()` con la lógica del cuaderno; se guarda el SHA-256 del cuaderno. Incluye la interpolación lineal que el cuaderno aplica **solo** para STL. | `servicios/fuente_original.py` |
| T7 | Agregado climático mensual/anual por estación | clima | memoria | Semanas asignadas al mes de su fecha de cierre; TMAX/TMIN promedio y PRECIP suma de semanas con dato; se informa el número de semanas. | `analitica.clima_mensual_por_estacion` |
| T8 | Agregado por estado | T7 / clima | memoria | Promedio simple de estaciones con dato; se informa número de estaciones y rango. | `analitica.clima_por_estado`, `clima_semanal_estado` |
| T9 | Serie de precio por estado de origen | precios | memoria | Misma regla del cuaderno final (promedio diario y `resample("W")`) filtrada por `estado_aux`. | `analitica.serie_precio_semanal_por_estado` |
| T10 | Unión precio–clima | T8 + T9 | memoria | Llave semana: `fecha_clima + 4 días` (miércoles → domingo). `validate="one_to_one"`; se reportan filas emparejadas y no emparejadas. Las cifras resumen usan solo las semanas emparejadas; la gráfica muestra, en el periodo comparado, todos los registros de cada fuente y sombrea en el panel del precio los tramos sin cotizaciones. | `analitica.unir_precio_clima` |
| T11 | EDA por año y mes | serie T6 | memoria | Agrupación por año/mes de semanas con dato; NaN excluidos. | `analitica.matriz_anio_mes` |
| T12 | Mínimos y máximos | precios | memoria | `min/max` sobre valores registrados, con su fecha. | `analitica.resumen_min_max` |
| T13 | Conteos frente a umbrales | T8 | memoria | Semanas cuyo promedio estatal cumple el umbral documentado; comparación estricta (`>`/`<`). | `analitica.conteo_umbrales` |

## Efecto documentado de la imputación del cuaderno final
`descomponer_estacionalidad()` aplica `semanal.interpolate(limit_direction="both")` antes de STL. El panel "Serie usada en la descomposición" muestra ese resultado y se rotula como tal. En el resto del sitio las semanas sin dato aparecen como huecos.

## 4. Granularidades y agregaciones

| Serie | Frecuencia de origen | Presentación |
|---|---|---|
| Precios de granos | Semanal (miércoles) | Diario/semanal en `/precios/`; semanal (cierre domingo) en series |
| Precios de hortalizas | Diaria (lunes a viernes) | Diaria en `/precios/`; promedio diario y semanal en series |
| Clima | Semanal (cierre miércoles) | Semanal; mensual y anual por agregación |

- Los ejes temporales usan fechas reales; el formato de etiqueta pasa de años a meses y días según el intervalo visible. Nunca se muestra un nivel más fino que la frecuencia de origen.
- Promedios anual/mensual de precio (`/analisis/`): media de los valores semanales con dato de cada periodo; el tooltip indica cuántas semanas intervienen.
- Precipitación mensual/anual (`/sequia/`) y en mapas: suma de las semanas cuyo cierre cae en el periodo. Temperaturas: promedio de las semanas con dato. Una semana que cruza dos meses se asigna al mes de su fecha de cierre.
- Valores estatales: promedio simple de las estaciones del estado con dato en la semana.
- Títulos del eje horizontal: las series semanales se rotulan con la fecha en que termina cada semana: «Fecha de cierre de la semana (miércoles)» para el clima y las series del modelado (W-WED) y «Fecha de cierre de la semana (domingo)» para las series de precio del cuaderno (`resample("W")`). En «Precio y clima» el eje («Fecha de cierre de la semana (domingo)») es el de la semana de precios, porque cada semana climática se asigna a la semana de precio que la contiene. Las cotizaciones de `/precios/` usan «Fecha de cotización». En las gráficas con selector de periodo, el título cambia con la vista: «Año» o «Mes» en los promedios de precio y, en «Sequía y temperatura», el título del panel de precipitación (semanal, mensual o anual), mientras el eje compartido conserva la fecha de cierre semanal de la temperatura.

## 5. Umbrales

Centralizados en `agro/configuracion.py` (`UMBRALES_TERMICOS`) con comparación estricta; probados en `test_umbrales_limites`.

| Cultivo | Condición | Fuente en el reporte técnico |
|---|---|---|
| Maíz | TMAX > 32 °C | Tabla 1.1 y sección 3.3 |
| Maíz | TMIN < 14 °C | Secciones 2.1 y 3.3 |
| Haba | TMAX > 25 °C (límite inferior de 25–30 °C) | Sección 3.3 |

Completitud: el reporte excluye del modelado series con más de ~5 % de semanas faltantes (sección 6.3); la plataforma lo usa solo como referencia visual.

Los umbrales se refieren a condiciones diarias; el archivo climático contiene promedios semanales, por lo que los conteos son orientativos. Los insumos no incluyen un índice de sequía ni un umbral de precipitación aplicable a datos semanales; no se clasifica sequía.

### 5.1 Tiempo aproximado hasta la cosecha

La ficha de `/precios/` («Tiempo aproximado hasta la cosecha») es información agronómica contextual, independiente de los datos del SNIIM, del cuaderno y de los modelos; no es un calendario ni una recomendación para una parcela. El reporte técnico no contiene plazos de siembra a cosecha, por lo que se usaron publicaciones técnicas y académicas mexicanas (INIFAP, Colegio de Postgraduados y universidades), consultadas en noviembre de 2026. El contenido es una síntesis propia guardada en `agro/configuracion.py` (`CICLO_CULTIVO`); la página no hace solicitudes externas y los enlaces solo se abren si el usuario los sigue. Las cotizaciones del SNIIM no identifican la variedad, por lo que cada ficha nombra la variedad, la región y el manejo de su fuente en lugar de extrapolarlos.

| Producto | Intervalo mostrado | Inicio y fin | Variedad, región y manejo | Fuente |
|---|---|---|---|---|
| Maíz blanco | 140 a 150 días | Siembra → madurez fisiológica | Híbrido H-392, grano blanco, ciclo intermedio-tardío; Jalisco, Nayarit, Michoacán, Guerrero y Aguascalientes; principalmente temporal | Ramírez-Díaz et al. (2022), Rev. Fitotec. Mex. 45(4): 523-525, https://doi.org/10.35196/rfm.2022.4.523 |
| Frijol negro | 90 a 100 días | Siembra → madurez fisiológica (grano seco) | San Luis 22; centro-norte (Guanajuato, Querétaro, San Luis Potosí, Zacatecas); temporal | Anaya-López et al. (2025), Rev. Mex. Cienc. Agríc. 16(2): e3411, https://doi.org/10.29312/remexca.v16i2.3411 |
| Frijol pinto | 97 a 102 días | Siembra → madurez fisiológica (grano seco) | PID 1 (97 a 102 días) y Pinto Saltillo (102 días, ensayo 2017); Valle del Guadiana, Durango; riego | Rosales-Serna y Flores-Gallardo (2022), Rev. Fitotec. Mex. 45(1): 145-147; Rosales-Serna et al. (2019), Rev. Fitotec. Mex. 42(1): 39-46 (cuadro 5) |
| Haba | ~145 días; ~162 días | Siembra → madurez fisiológica; siembra → cosecha de grano seco | Cochinera y San Pedro; Montecillo, Estado de México (2,250 m); temporal con riegos de apoyo; siembra el 22 de mayo de 2003; un solo ciclo | Pichardo-Riego et al. (2007), Terra Latinoamericana 25(2): 145-154 |
| Maíz blanco pozolero | ~7 meses; ~9 meses | Siembra → madurez del grano; siembra → cosecha de grano seco | Cacahuacintle, raza pozolera de los Valles Altos (2,600-2,900 m), temporal, siembra de febrero a abril y cosecha en diciembre-enero; las cotizaciones provienen del Estado de México y el SNIIM no identifica la raza | Ramos Rodríguez (2022), Rev. Geogr. Agríc. 69, https://doi.org/10.5154/r.rga.2022.69.05 (el artículo indica unos 7 meses de la siembra a la madurez fisiológica del grano y un ciclo total de unos 9 meses) |
| Tomate saladette | 4 a 6 semanas; ~3 meses | Siembra en charola → trasplante; trasplante → primer corte | Invernadero: Hidalgo (siembra 8 de marzo, trasplante 15 de abril, primer corte «tres meses después del trasplante», 24 cortes hasta el 15 de diciembre); Nayarit (trasplante a los 26 días); Estado de México (trasplante a los 45 días) | Terrones Cordero (2019), Rev. Mex. Agronegocios 44: 170-183; Alejo-Santiago et al. (2024), Terra Latinoam. 42: e1992; Mejía-Betancourt et al. (2023), Rev. Mex. Cienc. Agríc. 14(3): 389-399 |
| Aguacate Hass | ~3 años; ~6 años; ~9 meses | Injerto → inicio de producción; injerto → plena producción; floración → madurez del fruto (cada temporada) | Árbol: huerto de temporal en Tepic, Nayarit (portainjertos plantados en julio de 2000, injertados en mayo de 2001). Fruto: Nuevo Parangaricutiro, Michoacán (2,050 m), floración en enero | Salazar-García et al. (2016), Rev. Chapingo Ser. Hortic. 22(3): 161-175, https://doi.org/10.5154/r.rchsh.2015.06.013; Tapia Vargas et al. (2014), Rev. Mex. Cienc. Agríc. 5(3): 463-472 |

Notas de la revisión:

- San Luis 22: el resumen del artículo indica 95 a 100 días a madurez fisiológica y la descripción de la planta, 90 a 95; se muestra el intervalo conjunto (90 a 100 días).
- Frijol y haba: el SNIIM cotiza grano seco. Para la haba la ficha indica que el plazo es el del grano seco y que la vaina verde se cosecha antes, sin dar una cifra para esta: la única referencia revisada con fechas de cosecha en verde (Pérez López et al., 2015, Rev. Mex. Cienc. Agríc. 6(7)) no informa el intervalo directamente y su cálculo a partir de fechas mezclaría localidades y ciclos.
- Aguacate: el establecimiento del árbol y el desarrollo anual del fruto se presentan por separado y no se suman.
- Maíz blanco pozolero: el SNIIM no identifica la raza; se usa el Cacahuacintle porque es el maíz pozolero de los Valles Altos y las cotizaciones provienen del Estado de México. No se incluye el elote.
- Tomate saladette: no se encontraron plazos publicados para campo abierto en Sinaloa o Puebla; los intervalos provienen de estudios en invernadero y la ficha lo indica. El intervalo de 4 a 6 semanas reúne los trasplantes a los 26, ~38 y 45 días de la siembra de las tres fuentes.

## 6. Limitaciones y discrepancias

- **Pronóstico.** La sección 5 de `Analisis_Precios_SNIIM_vf.ipynb` (SARIMA, SARIMAX, Koyck y STL por componentes; entrenamiento 2015–2024, prueba en las 53 semanas de 2025) se ejecuta fuera de la aplicación, en un kernel limpio y sin guardar el notebook. Sus resultados numéricos (serie W-WED, valores ajustados, pronósticos de 2025 y métricas) están en `data/derivados/modelado_vf.json`, junto con el SHA-256 de cada insumo; la aplicación solo muestra esos resultados si los hashes coinciden. No hay pronósticos posteriores a 2025.
- **Reproducción.** La ejecución en un kernel limpio (Python 3.13, pandas 2.3.3, numpy 2.5.3, statsmodels 0.15.0, scipy 1.18.1) reproduce todas las selecciones del notebook (órdenes, rezagos, Koyck y modelos STL). De las 65 métricas de 2025, 59 coinciden con las salidas guardadas al redondeo; el SARIMAX del haba difiere 0.11 % (RMSE 10.664 frente a 10.652). Las cuatro variantes STL del haba difieren 17–18 % (RMSE 5.965 frente a 5.089): el ARIMA(2,1,1) de la tendencia tiene una verosimilitud casi plana (varianza en su cota inferior y MA cerca de 1), y el optimizador converge a óptimos distintos según el entorno numérico (AIC −4510.42 aquí frente a −4534.58 guardado). La plataforma usa los valores reproducidos.
- **Aguacate Hass.** `Precio Frec` supera a `Precio Max` en el 100 % de los registros y `Precio Mín` está vacío: posible desplazamiento de columnas en la fuente. Se conservan los valores y la interfaz muestra una nota de interpretación. La comparación se hace dentro de cada registro (misma fecha, presentación y origen); la nota se calcula con los registros de la selección e indica si la condición afecta a todos o a una parte.
- **Nombres públicos.** La interfaz muestra «Tomate saladette» y «Aguacate Hass»: «Primera» es la única clasificación con la que aparecen en los datos, por lo que no distingue productos. Los datos, filtros y URL conservan el nombre original (`NOMBRE_PUBLICO` en `agro/configuracion.py`).
- **Clima sin coordenadas, municipio ni cultivo.** Los mapas representan promedios estatales en la capital de cada estado (`REFERENCIA_ESTADOS`); las estaciones no se asocian a cultivos. Con columnas `LATITUD`/`LONGITUD` el mapa usa la ubicación real. Al seleccionar un estado, el mapa muestra solo sus datos: con coordenadas de estaciones ajusta la vista a sus límites (`fit_bounds`, zoom máximo 8); sin ellas, se centra en el punto de referencia del estado (zoom 7).
- **Estados sin clima.** México (maíz blanco 2015 y maíz pozolero) y `Todos` (aguacate) no tienen correspondencia climática; no se fuerzan alias.
- **STL.** El cuaderno final interpola linealmente las semanas faltantes antes de la descomposición; el primer panel lo indica.
- **Cortes en las gráficas.** Las líneas se interrumpen cuando transcurre al menos una semana de calendario sin registros (en las cotizaciones diarias se inserta un valor nulo solo en la capa de visualización). Los intervalos de cuatro semanas o más (`HUECO_MIN_SEMANAS`) se sombrean y se describen con las fechas de la última observación previa y de la siguiente. Ejemplo verificado: Frijol Negro con origen en Puebla tiene 9 cotizaciones, sin registros entre el 1 de noviembre de 2017 y el 4 de julio de 2018 (34 semanas). La fuente no indica la causa.
- **Última semana en el análisis por año y mes.** La serie semanal rotula cada semana con su domingo de cierre; la última (cierre el 4 de enero de 2026) solo contiene cotizaciones del 29 al 31 de diciembre de 2025, porque el archivo de precios termina el 31 de diciembre de 2025. En «Análisis por año y mes» su fecha de referencia es la última fecha del archivo y se agrupa en diciembre de 2025; no se ofrece ni se acepta 2026. La serie semanal y los modelos no cambian.
- **Cobertura del clima.** «Clima», «Sequía y temperatura» y «Precio y clima» usan `Clima_Municipios_Top50_Semanal_v1.csv` (semanas con cierre del 7 de enero de 2015 al 1 de enero de 2025); por eso 2025 solo ofrece enero. El modelado usa los archivos v2 ponderados por producción, que llegan al 31 de diciembre de 2025 y tienen otra red de estaciones; no se sustituyen entre sí.
- **STL aditiva.** La descomposición se aplica al precio sin transformar; tendencia, estacionalidad y residuo se expresan en MXN/kg, y los dos últimos como desviaciones alrededor de cero.
- **Imputación.** El modelado imputa precios (interpolación lineal y propagación en los extremos) y clima (interpolación de huecos de hasta 4 semanas y climatología de entrenamiento); las semanas imputadas no se usan para evaluar. La plataforma muestra como serie observada solo las semanas con cotización.
- **Clima.** Los mapas, Sequía y Precio y clima usan `Clima_Municipios_Top50_Semanal_v1.csv` (promedio estatal). El modelado usa los archivos v2, con clima por cultivo ponderado por la producción de los municipios asignados; v2 cubre 2025 y tiene otro conjunto de estaciones (43 de 83 en común con v1).

## 7. Mapas base

Leaflet 1.9.4 (licencia BSD-2) se sirve desde `agro/static/agro/vendor/leaflet/`, y la capa de límites estatales desde `agro/static/agro/geo/mexico_estados.geojson`: Natural Earth 1:10 m, dominio público, simplificada a 0.003° (procedencia y transformaciones en `agro/static/agro/geo/FUENTE.txt`). Esa capa se dibuja en ambos modos de ejecución; los puntos se ubican en sus coordenadas reales y se conservan el ajuste a la selección, el zoom, el desplazamiento, las etiquetas emergentes y la leyenda.

- **Modo local (sin Internet).** El fondo es la capa local de límites estatales; no se solicitan mosaicos ni otros recursos externos.
- **Modo público (ngrok).** Sobre los mosaicos de `https://tile.openstreetmap.org/{z}/{x}/{y}.png` (atribución © colaboradores de OpenStreetMap) se dibuja solo el contorno de los estados. La política de uso de mosaicos de OpenStreetMap exige el encabezado `Referer`; con `SECURE_REFERRER_POLICY = "same-origin"` el servidor respondía 403, por lo que se usa `strict-origin-when-cross-origin`. CartoDB no se usa porque la versión instalada de Folium indica que requiere clave de API. El zoom está limitado (3–12) y no se precargan ni almacenan mosaicos.

## 8. Pruebas

`agro/tests/test_plataforma.py` verifica: hashes; validación de ambos archivos; importación sin pérdida ni alteración de valores (comparación celda a celda con los CSV); ausencia de relleno; series idénticas a las funciones del cuaderno final (secciones 1 a 4); ausencia de dependencias de archivos retirados; unidades y títulos de ejes; paleta sin azul predeterminado; escala cálida de sequía con umbrales sin cambio; cortes y notas de discontinuidad; pronóstico de evaluación visible por defecto; filtros dependientes calculados con los datos y validados en el servidor; parámetros manipulados sin error 500; igualdad de pronósticos, métricas y series con los resultados guardados; cardinalidad y ausencia de fuga temporal en la unión precio–clima; rutas, filtros, estados vacíos y errores; ejes temporales con detalle progresivo; selector anual/mensual sin granularidad inventada; mosaicos y política `Referrer-Policy`; ausencia de recursos externos en modo local, recursos locales de mapas y licencias, configuración de los modos local y público; CSRF directo y vía proxy HTTPS; hosts no permitidos; `DEBUG=False`; ausencia de secretos, textos internos y referencias no permitidas.
