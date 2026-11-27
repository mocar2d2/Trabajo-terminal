from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="CargaDatos",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("archivo", models.CharField(max_length=255)),
                ("tipo", models.CharField(max_length=20)),
                ("sha256", models.CharField(max_length=64)),
                ("filas_origen", models.IntegerField()),
                ("filas_importadas", models.IntegerField()),
                ("reporte", models.JSONField(default=dict)),
                ("creada", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-creada"]},
        ),
        migrations.CreateModel(
            name="ClimaRegistro",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fila_origen", models.IntegerField(unique=True)),
                ("fecha", models.DateField(db_index=True)),
                ("precip", models.FloatField(null=True)),
                ("tmax", models.FloatField(null=True)),
                ("tmin", models.FloatField(null=True)),
                ("id_estacion", models.IntegerField(db_index=True)),
                ("estado", models.CharField(db_index=True, max_length=80)),
                ("latitud", models.FloatField(null=True)),
                ("longitud", models.FloatField(null=True)),
            ],
            options={"ordering": ["fila_origen"]},
        ),
        migrations.CreateModel(
            name="PrecioRegistro",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fila_origen", models.IntegerField(unique=True)),
                ("fecha_texto", models.CharField(blank=True, max_length=20, null=True)),
                ("fecha", models.DateField(db_index=True, null=True)),
                ("origen", models.CharField(blank=True, max_length=80, null=True)),
                ("precio_min", models.FloatField(null=True)),
                ("precio_max", models.FloatField(null=True)),
                ("precio_frec", models.FloatField(null=True)),
                ("producto", models.CharField(db_index=True, max_length=120)),
                ("categoria", models.CharField(max_length=40)),
                ("anio", models.IntegerField(null=True)),
                ("mes", models.FloatField(null=True)),
                ("semana", models.FloatField(null=True)),
                ("presentacion", models.CharField(blank=True, max_length=80, null=True)),
                ("origen_estado", models.CharField(blank=True, max_length=80, null=True)),
                ("cultivo_aux", models.CharField(db_index=True, max_length=40)),
                ("estado_aux", models.CharField(blank=True, db_index=True, max_length=80, null=True)),
            ],
            options={"ordering": ["fila_origen"]},
        ),
        migrations.CreateModel(
            name="SerieAnalisis",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("producto", models.CharField(max_length=120, unique=True)),
                ("resultado", models.JSONField()),
                ("sha256_fuente", models.CharField(max_length=64)),
                ("creada", models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
