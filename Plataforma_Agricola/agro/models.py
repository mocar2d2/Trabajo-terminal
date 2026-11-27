"""Modelos de almacenamiento de los insumos importados.

Cada registro conserva el numero de fila del CSV original y los valores tal
como aparecen en la fuente. Las columnas auxiliares se identifican con el
sufijo _aux y nunca sustituyen a las originales.
"""
from django.db import models


class CargaDatos(models.Model):
    archivo = models.CharField(max_length=255)
    tipo = models.CharField(max_length=20)  # precios | clima | analisis
    sha256 = models.CharField(max_length=64)
    filas_origen = models.IntegerField()
    filas_importadas = models.IntegerField()
    reporte = models.JSONField(default=dict)
    creada = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-creada"]


class PrecioRegistro(models.Model):
    fila_origen = models.IntegerField(unique=True)
    fecha_texto = models.CharField(max_length=20, null=True, blank=True)
    fecha = models.DateField(null=True, db_index=True)
    origen = models.CharField(max_length=80, null=True, blank=True)
    precio_min = models.FloatField(null=True)
    precio_max = models.FloatField(null=True)
    precio_frec = models.FloatField(null=True)
    producto = models.CharField(max_length=120, db_index=True)
    categoria = models.CharField(max_length=40)
    anio = models.IntegerField(null=True)
    mes = models.FloatField(null=True)
    semana = models.FloatField(null=True)
    presentacion = models.CharField(max_length=80, null=True, blank=True)
    origen_estado = models.CharField(max_length=80, null=True, blank=True)
    # Auxiliares documentadas en docs/METODOLOGIA.md
    cultivo_aux = models.CharField(max_length=40, db_index=True)
    estado_aux = models.CharField(max_length=80, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["fila_origen"]


class ClimaRegistro(models.Model):
    fila_origen = models.IntegerField(unique=True)
    fecha = models.DateField(db_index=True)
    precip = models.FloatField(null=True)
    tmax = models.FloatField(null=True)
    tmin = models.FloatField(null=True)
    id_estacion = models.IntegerField(db_index=True)
    estado = models.CharField(max_length=80, db_index=True)
    latitud = models.FloatField(null=True)
    longitud = models.FloatField(null=True)

    class Meta:
        ordering = ["fila_origen"]


class SerieAnalisis(models.Model):
    """Series de precios de las secciones 1 a 4 del cuaderno final (fuente_original.resumen_producto)."""

    producto = models.CharField(max_length=120, unique=True)
    resultado = models.JSONField()
    sha256_fuente = models.CharField(max_length=64)
    creada = models.DateTimeField(auto_now_add=True)
