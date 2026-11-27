"""Catalogos y umbrales centralizados.

Cada valor esta documentado con su fuente. Ningun umbral se usa para
clasificar sequias: la fuente no contiene un indice de sequia (ver
docs/METODOLOGIA.md). Los umbrales termicos se muestran solo como
referencias documentadas en el reporte tecnico.
"""

# Correspondencia explicita producto (columna Producto_Buscado) -> cultivo.
# Es una columna auxiliar; el nombre original del producto se conserva.
PRODUCTO_A_CULTIVO = {
    "Maíz blanco": "Maíz",
    "Maíz blanco pozolero": "Maíz",
    "Frijol Pinto": "Frijol",
    "Frijol Negro": "Frijol",
    "Haba": "Haba",
    "Tomate Saladette - Primera": "Tomate",
    "Aguacate Hass - Primera": "Aguacate",
}

CULTIVOS_ORDEN = ["Maíz", "Frijol", "Haba", "Tomate", "Aguacate"]

# Nombre público de cada producto (solo presentación). Internamente se conserva el
# nombre original de Producto_Buscado. «Primera» es la única clasificación con la que
# aparecen el tomate saladette y el aguacate Hass en los datos, por lo que no distingue
# entre productos y se omite; los nombres comunes van en minúscula salvo nombres propios.
NOMBRE_PUBLICO = {
    "Maíz blanco": "Maíz blanco",
    "Maíz blanco pozolero": "Maíz blanco pozolero",
    "Frijol Pinto": "Frijol pinto",
    "Frijol Negro": "Frijol negro",
    "Haba": "Haba",
    "Tomate Saladette - Primera": "Tomate saladette",
    "Aguacate Hass - Primera": "Aguacate Hass",
}


def nombre_publico(producto):
    return NOMBRE_PUBLICO.get(producto, producto)

# Tiempo aproximado de la siembra (o del injerto) a la cosecha, por producto.
# Síntesis propia de fuentes técnicas mexicanas; es información contextual,
# independiente de los datos de precios y de los modelos (ver docs/METODOLOGIA.md,
# «Tiempo aproximado hasta la cosecha»). No se extrapola entre variedades ni
# regiones: cuando no hay una referencia aplicable se indica en lugar de una cifra.
# Las fichas se guardan en el proyecto; consultarlas no requiere Internet.
CICLO_CULTIVO = {
    "Maíz blanco": {
        "etapas": [
            ("De la siembra a la madurez fisiológica del grano", "140 a 150 días"),
        ],
        "contexto": (
            "Referencia de un híbrido de maíz de grano blanco (H-392) de ciclo intermedio-tardío, "
            "evaluado por el INIFAP en regiones de subtrópico y transición de Jalisco, Nayarit, "
            "Michoacán, Guerrero y Aguascalientes, principalmente de temporal. Las cotizaciones del "
            "SNIIM no identifican la variedad. El grano se cosecha después de su madurez fisiológica."
        ),
        "referencias": [
            {
                "texto": "Ramírez-Díaz, J. L. et al. (2022). H-392: híbrido de maíz de grano blanco para "
                         "regiones agrícolas del subtrópico y transición de México. Revista Fitotecnia "
                         "Mexicana, 45(4), 523-525. INIFAP.",
                "url": "https://doi.org/10.35196/rfm.2022.4.523",
            },
        ],
    },
    "Maíz blanco pozolero": {
        "etapas": [
            ("De la siembra a la madurez del grano", "Alrededor de 7 meses"),
            ("De la siembra a la cosecha de grano seco", "Alrededor de 9 meses"),
        ],
        "contexto": (
            "Referencia del maíz Cacahuacintle, el maíz pozolero de los Valles Altos del centro de "
            "México, sembrado en temporal entre febrero y abril a 2,600-2,900 m de altitud; el grano "
            "se cosecha en diciembre y enero. Las cotizaciones de este producto provienen del Estado de "
            "México, pero el SNIIM no identifica la raza. No se incluye la venta como elote."
        ),
        "referencias": [
            {
                "texto": "Ramos Rodríguez, A. (2022). Origen e historia natural y humana de Cacahuacintle, una "
                         "raza mexicana de maíz. Revista de Geografía Agrícola, 69. Universidad Autónoma Chapingo.",
                "url": "https://doi.org/10.5154/r.rga.2022.69.05",
            },
        ],
    },
    "Frijol Negro": {
        "etapas": [
            ("De la siembra a la madurez fisiológica", "90 a 100 días"),
        ],
        "contexto": (
            "Variedad San Luis 22, de frijol negro para temporal en el centro-norte de México "
            "(Guanajuato, Querétaro, San Luis Potosí y Zacatecas), liberada por el INIFAP. El SNIIM "
            "cotiza frijol en grano seco, que se cosecha después de esta etapa, y no identifica la variedad."
        ),
        "referencias": [
            {
                "texto": "Anaya-López, J. L. et al. (2025). ‘San Luis 22’: variedad de frijol negro brillante "
                         "de temporal para el centro-norte de México. Revista Mexicana de Ciencias "
                         "Agrícolas, 16(2), e3411. INIFAP.",
                "url": "https://doi.org/10.29312/remexca.v16i2.3411",
            },
        ],
    },
    "Frijol Pinto": {
        "etapas": [
            ("De la siembra a la madurez fisiológica", "97 a 102 días"),
        ],
        "contexto": (
            "Variedades Pinto Saltillo (102 días en el ensayo de 2017) y PID 1 (97 a 102 días), "
            "evaluadas por el INIFAP bajo riego en el Valle del Guadiana, Durango. En temporal o en "
            "otras regiones el ciclo puede diferir. El SNIIM cotiza frijol en grano seco, que se "
            "cosecha después de esta etapa, y no identifica la variedad."
        ),
        "referencias": [
            {
                "texto": "Rosales-Serna, R. y Flores-Gallardo, H. (2022). PID 1: variedad de frijol pinto con "
                         "semillas de oscurecimiento lento para riego en Durango, México. Revista "
                         "Fitotecnia Mexicana, 45(1), 145-147. INIFAP.",
                "url": "https://revistafitotecniamexicana.org/documentos/45-1/15a.pdf",
            },
            {
                "texto": "Rosales-Serna, R. et al. (2019). Rendimiento y calidad de grano en líneas mejoradas "
                         "de frijol cultivadas bajo riego en Durango, México. Revista Fitotecnia Mexicana, "
                         "42(1), 39-46. INIFAP.",
                "url": "https://revistafitotecniamexicana.org/documentos/42-1/5a.pdf",
            },
        ],
    },
    "Haba": {
        "etapas": [
            ("De la siembra a la madurez fisiológica", "Alrededor de 145 días"),
            ("De la siembra a la cosecha de grano seco", "Alrededor de 162 días"),
        ],
        "contexto": (
            "Cultivares Cochinera y San Pedro sembrados el 22 de mayo de 2003 en Montecillo, Estado de "
            "México (2,250 m de altitud), en temporal con riegos de apoyo cerca de la siembra; "
            "corresponde a un solo ciclo de estudio. El plazo es el de la haba cosechada como grano "
            "seco, que es la que se cotiza aquí; la haba en vaina verde se cosecha antes."
        ),
        "referencias": [
            {
                "texto": "Pichardo-Riego, J. C. et al. (2007). Aplicación dividida de nitrógeno y eficiencia "
                         "agronómica de nitrógeno, uso de agua y radiación, y rendimiento de haba. Terra "
                         "Latinoamericana, 25(2), 145-154. Colegio de Postgraduados.",
                "url": "https://terralatinoamericana.org.mx/index.php/terra/article/download/1420/1612",
            },
        ],
    },
    "Tomate Saladette - Primera": {
        "etapas": [
            ("De la siembra en charola al trasplante", "Aproximadamente 4 a 6 semanas"),
            ("Del trasplante al primer corte", "Aproximadamente 3 meses"),
        ],
        "contexto": (
            "Referencias de jitomate saladette en invernadero: en Hidalgo la plántula se trasplantó "
            "unas 5 semanas después de la siembra, el primer corte llegó tres meses después del "
            "trasplante y los cortes siguieron unos 5 meses; en Nayarit y en el Estado de México el "
            "trasplante se hizo a los 26 y a los 45 días de la siembra. Los tomates cotizados provienen "
            "de Sinaloa y Puebla; en campo abierto y en esas regiones los tiempos pueden ser distintos."
        ),
        "referencias": [
            {
                "texto": "Terrones Cordero, A. (2019). Producción de jitomate en invernadero en San Juan "
                         "Tilcuautla, Hidalgo, México. Revista Mexicana de Agronegocios, 44, 170-183. "
                         "Universidad Autónoma del Estado de Hidalgo.",
                "url": "https://www.redalyc.org/journal/141/14161295005/html/",
            },
            {
                "texto": "Alejo-Santiago, G. et al. (2024). Requerimiento nutrimental de tomate tipo saladette "
                         "cosechado a dos racimos. Terra Latinoamericana, 42, e1992.",
                "url": "https://doi.org/10.28940/terra.v42i.1992",
            },
            {
                "texto": "Mejía-Betancourt, F. de los Á. et al. (2023). Esquejes enraizados, una alternativa para "
                         "la producción de jitomate bajo invernadero en ciclos cortos. Revista Mexicana de "
                         "Ciencias Agrícolas, 14(3), 389-399.",
                "url": "https://doi.org/10.29312/remexca.v14i3.3038",
            },
        ],
    },
    "Aguacate Hass - Primera": {
        "etapas": [
            ("Del injerto al inicio de la producción", "Alrededor de 3 años"),
            ("Del injerto a la plena producción", "Alrededor de 6 años"),
            ("De la floración a la madurez del fruto, en cada temporada", "Alrededor de 9 meses"),
        ],
        "contexto": (
            "El aguacate es un árbol perenne: una vez establecido produce cada año, por lo que el "
            "desarrollo del fruto no se suma al tiempo de establecimiento. Los plazos del árbol "
            "provienen de un huerto de temporal en Tepic, Nayarit, con portainjertos plantados en julio "
            "de 2000 e injertados con Hass en mayo de 2001; el del fruto, de un huerto en Nuevo "
            "Parangaricutiro, Michoacán (2,050 m), con floración en enero."
        ),
        "referencias": [
            {
                "texto": "Salazar-García, S. et al. (2016). Influence of clonal rootstocks on leaf nutrient "
                         "concentrations in ‘Hass’ avocado grown without irrigation. Revista Chapingo Serie "
                         "Horticultura, 22(3), 161-175. INIFAP.",
                "url": "https://doi.org/10.5154/r.rchsh.2015.06.013",
            },
            {
                "texto": "Tapia Vargas, L. M. et al. (2014). Nutrición orgánica del aguacate cv. «Hass» y "
                         "efecto nutrimental y agronómico. Revista Mexicana de Ciencias Agrícolas, 5(3), "
                         "463-472. INIFAP.",
                "url": "https://www.redalyc.org/pdf/2631/263130497010.pdf",
            },
        ],
    },
}

# Unidad de precio. El reporte tecnico (tabla 5.2) documenta MXN/kg para los
# granos del SNIIM. Para hortalizas la fuente no especifica la unidad; se
# muestra solo la moneda.
UNIDAD_PRECIO = {
    "granos": "MXN/kg",
    # El reporte final (main-04-11-26.pdf) documenta los precios del SNIIM en MXN/kg para los
    # cinco productos; la presentación (tamaño de caja) se conserva como dato descriptivo.
    "hortalizas": "MXN/kg",
}

# Parametros de Analisis_Precios_SNIIM_vf.ipynb (referencia; el calculo esta en
# agro/servicios/fuente_original.py).
PERIODO_ESTACIONAL_SEMANAS = 52
MIN_TRASLAPE_SEMANAS = 8

# Criterio de visualizacion (no altera datos): un intervalo de al menos este numero de
# semanas consecutivas sin registros se sombrea y se describe junto a la grafica. Las
# lineas se interrumpen siempre que falte al menos una semana.
HUECO_MIN_SEMANAS = 4

# Umbral de completitud documentado en el reporte tecnico (seccion 6.3):
# series con mas de ~5 % de semanas faltantes se excluyeron del modelado.
UMBRAL_FALTANTES_PCT = 5.0

# Umbrales termicos documentados en el reporte tecnico (secciones 1.2 y 3.3).
# Las temperaturas del archivo climatico son promedios semanales; comparar un
# promedio semanal con un umbral diario es una referencia, no un diagnostico.
UMBRALES_TERMICOS = [
    {
        "clave": "maiz_tmax",
        "cultivo": "Maíz",
        "variable": "TMAX",
        "operador": ">",
        "valor": 32.0,
        "descripcion": "Estrés térmico del maíz: temperatura máxima superior a 32 °C durante la floración.",
        "resumen": "Maíz: temperatura máxima superior a 32 °C",
        "corto": "Maíz: máxima > 32 °C",
        "fuente": "Reporte técnico, tabla 1.1 y sección 3.3",
    },
    {
        "clave": "maiz_tmin",
        "cultivo": "Maíz",
        "variable": "TMIN",
        "operador": "<",
        "valor": 14.0,
        "descripcion": "Las temperaturas mínimas inferiores a 14 °C reducen la productividad del maíz de temporal.",
        "resumen": "Maíz: temperatura mínima inferior a 14 °C",
        "corto": "Maíz: mínima < 14 °C",
        "fuente": "Reporte técnico, secciones 2.1 y 3.3",
    },
    {
        "clave": "haba_tmax",
        "cultivo": "Haba",
        "variable": "TMAX",
        "operador": ">",
        "valor": 25.0,
        "descripcion": "Las temperaturas de 25 a 30 °C durante la floración provocan la pérdida de flores y vainas del haba; se utiliza el límite inferior.",
        "resumen": "Haba: temperatura máxima superior a 25 °C",
        "corto": "Haba: máxima > 25 °C",
        "fuente": "Reporte técnico, sección 3.3",
    },
]


def cumple_umbral(valor, umbral):
    """Evalua un valor contra un umbral. None nunca cumple."""
    if valor is None:
        return False
    if umbral["operador"] == ">":
        return valor > umbral["valor"]
    if umbral["operador"] == "<":
        return valor < umbral["valor"]
    raise ValueError(f"Operador no soportado: {umbral['operador']}")


VARIABLES_CLIMA = {
    "TMAX": {"etiqueta": "Temperatura máxima", "unidad": "°C", "agregacion_mensual": "promedio"},
    "TMIN": {"etiqueta": "Temperatura mínima", "unidad": "°C", "agregacion_mensual": "promedio"},
    "PRECIP": {"etiqueta": "Precipitación", "unidad": "mm", "agregacion_mensual": "suma"},
}

# Nombres de los meses en minúscula, como corresponde en el texto corrido.
MESES = [
    (1, "enero"), (2, "febrero"), (3, "marzo"), (4, "abril"), (5, "mayo"), (6, "junio"),
    (7, "julio"), (8, "agosto"), (9, "septiembre"), (10, "octubre"), (11, "noviembre"),
    (12, "diciembre"),
]

# Puntos de referencia para representar en el mapa los valores agregados por
# estado: coordenadas aproximadas de la capital de cada entidad. El archivo
# climatico no incluye coordenadas de estaciones; estos puntos NO representan
# la ubicacion de ninguna estacion. Si el archivo climatico definitivo incluye
# columnas LATITUD y LONGITUD, el mapa usa las coordenadas reales.
REFERENCIA_ESTADOS = {
    "Aguascalientes": (21.882, -102.291),
    "Baja California": (32.625, -115.454),
    "Baja California Sur": (24.142, -110.313),
    "Campeche": (19.845, -90.524),
    "Chiapas": (16.753, -93.116),
    "Chihuahua": (28.632, -106.069),
    "Ciudad de México": (19.433, -99.133),
    "Coahuila": (25.423, -101.005),
    "Colima": (19.243, -103.725),
    "Durango": (24.027, -104.653),
    "Guanajuato": (21.019, -101.257),
    "Guerrero": (17.551, -99.501),
    "Hidalgo": (20.101, -98.759),
    "Jalisco": (20.659, -103.349),
    "México": (19.283, -99.656),
    "Michoacán": (19.706, -101.195),
    "Morelos": (18.922, -99.234),
    "Nayarit": (21.504, -104.894),
    "Nuevo León": (25.686, -100.316),
    "Oaxaca": (17.073, -96.726),
    "Puebla": (19.041, -98.206),
    "Querétaro": (20.588, -100.389),
    "Quintana Roo": (18.500, -88.296),
    "San Luis Potosí": (22.156, -100.985),
    "Sinaloa": (24.809, -107.394),
    "Sonora": (29.073, -110.956),
    "Tabasco": (17.989, -92.947),
    "Tamaulipas": (23.736, -99.146),
    "Tlaxcala": (19.318, -98.237),
    "Veracruz": (19.544, -96.910),
    "Yucatán": (20.967, -89.624),
    "Zacatecas": (22.771, -102.583),
}
