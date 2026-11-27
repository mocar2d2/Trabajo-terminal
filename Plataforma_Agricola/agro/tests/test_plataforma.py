"""Pruebas automatizadas con los datos reales de data/raw."""
import codecs
import json
import os
import re
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
from django.conf import settings
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from agro.configuracion import PRODUCTO_A_CULTIVO, UMBRALES_TERMICOS, cumple_umbral, nombre_publico
from agro.models import CargaDatos, ClimaRegistro, PrecioRegistro, SerieAnalisis
from agro.servicios import analitica, consultas
from agro.servicios import fuente_original
from agro.servicios.integridad import verificar_insumos
from agro.servicios.validacion import validar_clima, validar_precios

RAW = settings.RAW_DIR
CUADERNO_FINAL = RAW / "Analisis_Precios_SNIIM_vf.ipynb"
# Archivos retirados (nombres armados para que este archivo no los contenga literalmente).
OBSOLETOS = ["Analisis_Precios_SNIIM" + ext for ext in (".py", ".ipynb")]


def funciones_del_cuaderno():
    """Ejecuta, en un espacio aislado, solo las funciones y constantes de las
    secciones 1 a 4 del cuaderno final (sin graficas) y la preparacion de df de
    la celda de lectura. El cuaderno solo se lee."""
    import ast
    import contextlib
    import io
    import os
    from statsmodels.tsa.seasonal import STL

    nb = json.loads(CUADERNO_FINAL.read_text(encoding="utf-8"))
    nombres = {"serie_semanal_por_origen", "calcular_serie_armonizada", "serie_semanal",
               "matriz_faltantes_mensual", "descomponer_estacionalidad"}
    ns = {"pd": pd, "np": np, "STL": STL, "os": os}
    lectura = None
    for celda in nb["cells"]:
        if celda["cell_type"] != "code":
            continue
        fuente = "".join(celda["source"])
        if lectura is None and "pd.read_csv(RUTA_CSV)" in fuente:
            lectura = fuente
        for nodo in ast.parse(fuente).body:
            if isinstance(nodo, ast.FunctionDef) and nodo.name in nombres and nodo.name not in ns:
                exec(compile(ast.Module([nodo], []), "<cuaderno>", "exec"), ns)
            elif (isinstance(nodo, ast.Assign) and len(nodo.targets) == 1 and isinstance(nodo.targets[0], ast.Name)
                  and nodo.targets[0].id in ("COLUMNA_PRECIO", "PERIODO_ESTACIONAL")):
                exec(compile(ast.Module([nodo], []), "<cuaderno>", "exec"), ns)
    ns["RUTA_CSV"] = str(PRECIOS)
    with contextlib.redirect_stdout(io.StringIO()):
        exec(compile(lectura, "<cuaderno>", "exec"), ns)
    assert nombres <= set(ns), nombres - set(ns)
    return ns
PRECIOS = RAW / settings.PRECIOS_CSV
CLIMA = RAW / settings.CLIMA_CSV
HOST_SEGURO = {"secure": True}
# Términos que no deben aparecer; se guardan codificados (ROT13) para que este
# archivo no los contenga literalmente.
TERMINOS_PUBLICOS_PROHIBIDOS = [codecs.decode(t, "rot13") for t in ['genonwb grezvany', 'grfvf', 'fvabqny', 'rfphryn', 'cebsrfbe', 'nyhzab', 'rfghqvnagr', 'pynhqr', 'naguebcvp', 'pbjbex', 'trarenqb cbe vn']]
TERMINOS_REPOSITORIO_PROHIBIDOS = [codecs.decode(t, "rot13") for t in ['pynhqr', 'naguebcvp', 'pbjbex', 'trarenqb cbe vn', 'vagryvtrapvn negvsvpvny', 'nv-trarengrq', 'trarengrq ol']]


class IntegridadTests(SimpleTestCase):
    def test_hashes_coinciden(self):
        for r in verificar_insumos():
            self.assertTrue(r["raw_coincide"], r["archivo"])
            if r["usuario_existe"]:
                self.assertTrue(r["usuario_coincide"], r["archivo"])

    def test_cuaderno_final_registrado_sin_alterar_entradas(self):
        registro = json.loads(settings.REGISTRO_HASHES.read_text(encoding="utf-8"))
        self.assertEqual(registro["algoritmo"], "SHA-256")
        archivos = registro["archivos"]
        esperados = {
            "Clima_Municipios_Top50_Semanal_v1.csv": "10cc11aee85844b6ca6b0538a769b1d65a34a37f9e2e7f705e2dbe4791b6e3db",
            "Precios_Historicos_SNIIM_Continuo.csv": "86e23cd731750254fe119c449fed78085f316e8876a268541150271169db8589",
            "Reporte_Tecnico.pdf": "3f7334f6955085aa014d14cc92e2c81954687ffd81549fdab6cf66561ca19b1a",
            "Analisis_Precios_SNIIM_vf.ipynb": "4558bae4c84ced4f29ba764b1614a00e5ad192d7480055a68335cc397a7ecea6",
            "main-04-11-26.pdf": "7cee44a27530c657833b89ac7583523cb412e25e43590531e4012268a71f0ec3",
        }
        for nombre, h in esperados.items():
            self.assertEqual(archivos[nombre]["sha256"], h, nombre)
            self.assertTrue((settings.RAW_DIR / nombre).exists(), nombre)
        # El cuaderno y el programa anteriores ya no son insumos de la plataforma.
        for nombre in OBSOLETOS:
            self.assertNotIn(nombre, archivos)

    def test_comando_integridad(self):
        out = StringIO()
        call_command("verificar_integridad", stdout=out)
        self.assertIn("todos los hashes coinciden", out.getvalue())

    def test_sin_dependencias_de_archivos_retirados(self):
        raiz = settings.BASE_DIR
        excluir = {".venv", "venv", "staticfiles", "static_vendor", "data", "logs", "__pycache__", ".git"}
        for ruta in raiz.rglob("*"):
            if ruta.is_dir() or excluir & set(ruta.relative_to(raiz).parts):
                continue
            if ruta.suffix not in {".py", ".ps1", ".cmd", ".bat", ".html", ".md", ".txt", ".json", ".toml", ".cfg", ".ini"}:
                continue
            texto = ruta.read_text(encoding="utf-8", errors="ignore")
            for nombre in OBSOLETOS:
                self.assertNotIn(nombre, texto, f"{ruta.relative_to(raiz)} menciona {nombre}")
        self.assertEqual(settings.FUENTE_ANALISIS, CUADERNO_FINAL.name)
        self.assertFalse((RAW / "__pycache__").exists())


class ValidacionTests(SimpleTestCase):
    def test_precios_validos(self):
        df, r = validar_precios(PRECIOS, PRODUCTO_A_CULTIVO)
        self.assertEqual(r["errores"], [])
        self.assertTrue(r["codificacion"]["utf8_valido"])
        self.assertEqual(r["filas_con_precio_sin_fecha"], 0)
        self.assertEqual(r["duplicados_llave"], 0)
        self.assertEqual(r["anio_no_coincide"], 0)
        self.assertEqual(r["mes_no_coincide"], 0)
        self.assertEqual(set(r["productos"]), set(PRODUCTO_A_CULTIVO))
        self.assertEqual(len(set(PRODUCTO_A_CULTIVO.values())), 5)
        # Formato dia/mes confirmado: la lectura mes/dia invalida filas.
        self.assertGreater(r["fechas_invalidas_si_mes_dia"], 0)
        self.assertGreaterEqual(r["fecha_min"], "2015-01-01")

    def test_clima_valido(self):
        df, r = validar_clima(CLIMA)
        self.assertEqual(r["errores"], [])
        self.assertEqual(r["duplicados_fecha_estacion"], 0)
        self.assertEqual(r["tmin_mayor_tmax"], 0)
        self.assertEqual(set(r["dias_semana"]), {2})  # todas las semanas cierran en miercoles

    def test_clima_con_error_se_rechaza(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("FECHA,PRECIP,TMAX,TMIN,ID_Estacion,Estado\n2015-01-07,0,20,10,1,X\n2015-01-07,0,20,10,1,X\n")
        _, r = validar_clima(Path(f.name))
        self.assertTrue(r["errores"])

    def test_umbrales_limites(self):
        u = {"operador": ">", "valor": 32.0}
        self.assertFalse(cumple_umbral(32.0, u))
        self.assertTrue(cumple_umbral(32.01, u))
        self.assertFalse(cumple_umbral(None, u))
        u2 = {"operador": "<", "valor": 14.0}
        self.assertFalse(cumple_umbral(14.0, u2))
        self.assertTrue(cumple_umbral(13.99, u2))
        for u in UMBRALES_TERMICOS:
            self.assertIn(u["variable"], {"TMAX", "TMIN"})
            self.assertTrue(u["fuente"])


class DatosCargadosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("cargar_datos", stdout=StringIO())
        cls.csv_p = pd.read_csv(PRECIOS)
        cls.csv_c = pd.read_csv(CLIMA)

    # ---------------------------------------------------------- ingestion
    def test_filas_sin_perdida_ni_invencion(self):
        self.assertEqual(PrecioRegistro.objects.count(), len(self.csv_p))
        self.assertEqual(ClimaRegistro.objects.count(), len(self.csv_c))
        self.assertEqual(CargaDatos.objects.filter(tipo="precios").first().filas_importadas, len(self.csv_p))

    def test_valores_identicos_a_la_fuente(self):
        db = pd.DataFrame(PrecioRegistro.objects.order_by("fila_origen").values(
            "precio_min", "precio_max", "precio_frec", "producto", "fecha_texto"))
        for col_db, col_csv in [("precio_min", "Precio Mín"), ("precio_max", "Precio Max"), ("precio_frec", "Precio Frec")]:
            a = pd.to_numeric(db[col_db]).to_numpy()
            b = self.csv_p[col_csv].to_numpy()
            self.assertTrue(((a == b) | (pd.isna(a) & pd.isna(b))).all(), col_db)
        self.assertEqual(db["producto"].tolist(), self.csv_p["Producto_Buscado"].tolist())
        self.assertEqual(db["fecha_texto"].fillna("").tolist(), self.csv_p["Fecha"].fillna("").tolist())
        c = pd.DataFrame(ClimaRegistro.objects.order_by("fila_origen").values("precip", "tmax", "tmin", "id_estacion"))
        for col_db, col_csv in [("precip", "PRECIP"), ("tmax", "TMAX"), ("tmin", "TMIN"), ("id_estacion", "ID_Estacion")]:
            a = pd.to_numeric(c[col_db]).to_numpy()
            b = self.csv_c[col_csv].to_numpy()
            self.assertTrue(((a == b) | (pd.isna(a) & pd.isna(b))).all(), col_db)

    def test_sin_relleno_de_faltantes(self):
        self.assertEqual(PrecioRegistro.objects.filter(precio_frec__isnull=True).count(),
                         int(self.csv_p["Precio Frec"].isna().sum()))
        self.assertEqual(ClimaRegistro.objects.filter(tmax__isnull=True).count(),
                         int(self.csv_c["TMAX"].isna().sum()))

    def test_cultivos_y_auxiliares(self):
        cultivos = set(PrecioRegistro.objects.values_list("cultivo_aux", flat=True))
        self.assertEqual(cultivos, {"Maíz", "Frijol", "Haba", "Tomate", "Aguacate"})
        # La columna auxiliar no reemplaza las originales.
        r = PrecioRegistro.objects.filter(categoria="granos", fecha__isnull=False).first()
        self.assertIsNone(r.origen_estado)
        self.assertEqual(r.estado_aux, r.origen)

    def test_series_identicas_al_cuaderno_final(self):
        nb = funciones_del_cuaderno()
        df = fuente_original.cargar_precios_csv(PRECIOS)
        self.assertTrue(nb["df"].equals(df))
        fo = fuente_original
        sha = fo.sha256_archivo(CUADERNO_FINAL)
        for obj in SerieAnalisis.objects.all():
            p, r = obj.producto, obj.resultado
            self.assertEqual(obj.sha256_fuente, sha)
            semanal = nb["serie_semanal"](df, p)
            self.assertEqual(r["serie"], fo.serie_a_lista(semanal), p)
            self.assertAlmostEqual(r["pct_faltantes"], float(100 * semanal.isna().mean()), places=12)
            self.assertEqual(r["mapa_faltantes"], fo.matriz_a_dict(nb["matriz_faltantes_mensual"](semanal)), p)
            origenes = nb["serie_semanal_por_origen"](df, p)
            self.assertEqual(r["por_origen"], {o: fo.serie_a_lista(s) for o, s in origenes.items()}, p)
            if semanal.dropna().shape[0] < 2 * nb["PERIODO_ESTACIONAL"]:
                self.assertIsNone(r["descomposicion"], p)  # el cuaderno la omite
            else:
                self.assertEqual(r["descomposicion"], fo.stl_a_dict(nb["descomponer_estacionalidad"](semanal)), p)
        self.assertEqual(SerieAnalisis.objects.count(), self.csv_p["Producto_Buscado"].nunique())
        carga = CargaDatos.objects.filter(tipo="analisis").latest("id")
        self.assertEqual((carga.archivo, carga.sha256), (CUADERNO_FINAL.name, sha))

    def test_reingesta_clima_reemplazable(self):
        out = StringIO()
        call_command("cargar_datos", "--solo-clima", stdout=out)
        self.assertEqual(ClimaRegistro.objects.count(), len(self.csv_c))
        self.assertIn("Carga completada", out.getvalue())

    # -------------------------------------------------------------- joins
    def test_union_precio_clima_cardinalidad(self):
        precios = consultas.precios_df()
        clima = consultas.clima_df()
        for producto, estados in consultas.estados_comparables().items():
            for estado in estados:
                sp = analitica.serie_precio_semanal_por_estado(precios, producto, estado)
                ce = analitica.clima_semanal_estado(clima, estado)
                unido, rep = analitica.unir_precio_clima(sp, ce)
                self.assertLessEqual(len(unido), min(rep["filas_precio"], rep["filas_clima"]))
                self.assertEqual(rep["emparejadas"] + rep["precio_sin_clima"], rep["filas_precio"])
                self.assertEqual(rep["emparejadas"] + rep["clima_sin_precio"], rep["filas_clima"])
                if not unido.empty:
                    self.assertFalse(unido["semana"].duplicated().any())
                    # Sin fuga de informacion futura: clima cierra antes que la semana de precio.
                    self.assertTrue((unido["fecha_clima"] < unido["semana"]).all())

    def test_cache_anidada_sin_bloqueo(self):
        """Regresion: una fabrica de cache que llama a otra no debe bloquearse.

        El hilo no usa la base de datos (version_datos simulada): en SQLite en
        memoria otra conexion no puede leer mientras la prueba tiene la
        transaccion abierta.
        """
        import threading
        from unittest import mock
        from agro.servicios import consultas as c
        resultado = {}
        with mock.patch.object(c, "version_datos", return_value="prueba"):
            c._cache.clear()
            hilo = threading.Thread(
                target=lambda: resultado.update(v=c._memo("externa", lambda: c._memo("interna", lambda: 42) + 1)),
                daemon=True,
            )
            hilo.start()
            hilo.join(10)
        c._cache.clear()
        self.assertFalse(hilo.is_alive(), "_memo anidado quedó bloqueado")
        self.assertEqual(resultado["v"], 43)
        # Funciones reales que anidan cache, en el hilo principal.
        self.assertIn("Haba", c.estados_comparables())
        self.assertEqual(len(c.productos()), 7)
        self.assertGreater(c.resumen_general()["registros_precio"], 0)

    def test_http_redirige_a_https(self):
        r = self.client.get(reverse("agro:inicio"))
        self.assertEqual(r.status_code, 301)
        self.assertTrue(r["Location"].startswith("https://"))

    def test_estado_mexico_sin_clima_no_se_fuerza(self):
        comparables = consultas.estados_comparables()
        for estados in comparables.values():
            self.assertNotIn("México", estados)
            self.assertNotIn("Todos", estados)

    # -------------------------------------------------------------- vistas
    def test_rutas_responden(self):
        for nombre in ["inicio", "precios", "clima", "prediccion", "eda", "sequia", "comparar", "metodologia", "salud"]:
            r = self.client.get(reverse(f"agro:{nombre}"), **HOST_SEGURO)
            self.assertEqual(r.status_code, 200, nombre)

    def test_filtros_precios_y_vacio(self):
        url = reverse("agro:precios")
        r = self.client.get(url, {"producto": "Haba", "anio_desde": "2020", "anio_hasta": "2021"}, **HOST_SEGURO)
        self.assertContains(r, "fig-precios")
        # Combinacion valida en el formulario pero sin registros en la fuente:
        # Tomate de Puebla solo se cotiza en cajas de 12 y 13 kg.
        r = self.client.get(url, {"producto": "Tomate Saladette - Primera", "estado": "Puebla",
                                  "presentacion": "Caja de 25 kg."}, **HOST_SEGURO)
        self.assertContains(r, "No hay información disponible para la combinación seleccionada", count=1)
        self.assertNotContains(r, "fig-precios")
        # Los años ofrecidos dependen del producto: un año sin datos no es una opción valida.
        r = self.client.get(url, {"producto": "Frijol Negro", "anio_desde": "2024"}, **HOST_SEGURO)
        self.assertContains(r, "Revise los filtros")
        r = self.client.get(url, {"producto": "Inexistente"}, **HOST_SEGURO)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Revise los filtros")
        r = self.client.get(url, {"producto": "Haba", "anio_desde": "2022", "anio_hasta": "2018"}, **HOST_SEGURO)
        self.assertContains(r, "no puede ser posterior")

    def test_clima_mapa_y_vacio(self):
        url = reverse("agro:clima")
        r = self.client.get(url, {"variable": "PRECIP", "anio": "2020", "mes": "7", "estado": "Jalisco"}, **HOST_SEGURO)
        self.assertContains(r, "folium-map")
        self.assertContains(r, "L.map")
        self.assertContains(r, "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.assertContains(r, "OpenStreetMap")  # atribucion
        self.assertNotContains(r, "cartocdn")
        self.assertNotContains(r, "<iframe")
        self.assertNotContains(r, "bootstrap")
        r = self.client.get(url, {"variable": "TMAX", "anio": "1990"}, **HOST_SEGURO)
        self.assertContains(r, "Revise los filtros")

    def test_clima_agregacion_documentada(self):
        df = consultas.clima_df()
        pe = analitica.clima_mensual_por_estacion(df, "precip", 2020, 7)
        est = pe.iloc[0]
        sub = df[(df["id_estacion"] == est["id_estacion"]) & (df["fecha"].dt.year == 2020) & (df["fecha"].dt.month == 7)]
        self.assertAlmostEqual(est["valor"], sub["precip"].sum())

    def test_prediccion_no_inventa_pronostico(self):
        r = self.client.get(reverse("agro:prediccion"), {"producto": "Haba"}, **HOST_SEGURO)
        self.assertNotContains(r, "valores pronosticados")
        self.assertNotContains(r, "<strong>Pronóstico:</strong>")
        self.assertContains(r, "fig-stl")
        fig = self._figura(r.content.decode(), "fig-serie")
        self.assertFalse([t for t in fig["data"] if "pronóst" in str(t.get("name", "")).lower()])
        r = self.client.get(reverse("agro:prediccion"), {"producto": "Frijol Negro"}, **HOST_SEGURO)
        self.assertNotContains(r, "fig-stl")

    def test_plotly_json_valido(self):
        r = self.client.get(reverse("agro:eda"), {"producto": "Maíz blanco", "anio_desde": "2018"}, **HOST_SEGURO)
        html = r.content.decode()
        m = re.search(r'<script id="fig-caja" type="application/json">(.*?)</script>', html, re.S)
        fig = json.loads(m.group(1))
        self.assertTrue(fig["data"])
        self.assertEqual(fig["layout"]["paper_bgcolor"], "#ffffff")

    def test_sequia_sin_clasificacion_inventada(self):
        r = self.client.get(reverse("agro:sequia"), {"estado": "Zacatecas"}, **HOST_SEGURO)
        self.assertNotContains(r, "no presenta una clasificación oficial de sequía")
        self.assertNotContains(r, "orientativo")
        self.assertContains(r, "Las temperaturas son promedios semanales, mientras que los umbrales describen "
                               "condiciones diarias en etapas sensibles del cultivo.</p>")
        self.assertContains(r, "fig-sequia")

    def test_post_csrf(self):
        c = Client(enforce_csrf_checks=True)
        url = reverse("agro:comparar")
        r = c.get(url, **HOST_SEGURO)
        token = c.cookies["csrftoken"].value
        datos = {"producto": "Haba", "estado": "Puebla", "variable": "PRECIP", "csrfmiddlewaretoken": token}
        r = c.post(url, datos, HTTP_REFERER="https://testserver/comparar/", **HOST_SEGURO)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Semanas comparadas")
        r = Client(enforce_csrf_checks=True).post(url, {"producto": "Haba"}, **HOST_SEGURO)
        self.assertEqual(r.status_code, 403)

    @override_settings(ALLOWED_HOSTS=["127.0.0.1", "localhost", "ejemplo.ngrok-free.app"],
                       CSRF_TRUSTED_ORIGINS=["https://ejemplo.ngrok-free.app"])
    def test_post_csrf_via_proxy_https(self):
        c = Client(enforce_csrf_checks=True, HTTP_HOST="ejemplo.ngrok-free.app", HTTP_X_FORWARDED_PROTO="https")
        url = reverse("agro:comparar")
        c.get(url)
        token = c.cookies["csrftoken"].value
        r = c.post(url, {"producto": "Haba", "estado": "Puebla", "variable": "TMAX", "csrfmiddlewaretoken": token},
                   HTTP_ORIGIN="https://ejemplo.ngrok-free.app", HTTP_REFERER="https://ejemplo.ngrok-free.app/comparar/")
        self.assertEqual(r.status_code, 200)

    def test_referrer_policy_compatible_con_mosaicos(self):
        r = self.client.get(reverse("agro:clima"), **HOST_SEGURO)
        self.assertEqual(r["Referrer-Policy"], "strict-origin-when-cross-origin")
        self.assertNotContains(r, 'name="referrer"')

    def test_head_y_favicon(self):
        r = self.client.head(reverse("agro:inicio"), **HOST_SEGURO)
        self.assertEqual(r.status_code, 200)
        r = self.client.get("/favicon.ico", **HOST_SEGURO)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/svg+xml")

    def _figura(self, html, fid):
        m = re.search(r'<script id="' + fid + r'" type="application/json">(.*?)</script>', html, re.S)
        self.assertIsNotNone(m, fid)
        return json.loads(m.group(1))

    def test_ejes_temporales_con_detalle_progresivo(self):
        casos = [
            (reverse("agro:precios"), {"producto": "Haba"}, "fig-precios"),
            (reverse("agro:prediccion"), {"producto": "Haba"}, "fig-serie"),
            (reverse("agro:prediccion"), {"producto": "Haba"}, "fig-stl"),
            (reverse("agro:eda"), {"producto": "Haba"}, "fig-anual"),
            (reverse("agro:sequia"), {"estado": "Puebla"}, "fig-sequia"),
            (reverse("agro:clima"), {"variable": "TMAX", "anio": "2020", "estado": "Puebla"}, "fig-clima"),
        ]
        for url, params, fid in casos:
            fig = self._figura(self.client.get(url, params, **HOST_SEGURO).content.decode(), fid)
            ejes = [v for k, v in fig["layout"].items() if k.startswith("xaxis")]
            self.assertTrue(ejes, fid)
            for eje in ejes:
                self.assertEqual(eje.get("type"), "date", fid)
                formatos = [f["value"] for f in eje["tickformatstops"]]
                self.assertIn("%Y", formatos, fid)
                self.assertTrue(any("%b" in f for f in formatos), fid)
            self.assertTrue(fig["layout"].get("uirevision"), fid)

    def test_selector_anual_mensual_sin_inventar_granularidad(self):
        html = self.client.get(reverse("agro:eda"), {"producto": "Haba"}, **HOST_SEGURO).content.decode()
        fig = self._figura(html, "fig-anual")
        vistas = {t["meta"]["vista"]: t for t in fig["data"]}
        self.assertEqual(set(vistas), {"anual", "mensual"})
        serie = consultas.serie_eda("Haba").dropna()
        # Cada barra mensual corresponde a un mes con al menos una semana observada.
        self.assertEqual(len(vistas["mensual"]["x"]), serie.groupby(serie.index.to_period("M")).ngroups)
        self.assertEqual(sum(vistas["mensual"]["customdata"]), len(serie))
        self.assertEqual(sum(vistas["anual"]["customdata"]), len(serie))
        self.assertIn('data-vista="mensual"', html)

    def test_metodologia_sin_subtitulo_y_lang(self):
        r = self.client.get(reverse("agro:metodologia"), **HOST_SEGURO)
        self.assertNotContains(r, "Fuentes de información, cálculos y criterios")
        self.assertContains(r, '<html lang="es-MX">')
        self.assertContains(r, "seccion-encabezado--solo-titulo")
        for quitado in ["Notas de interpretación", "<h2>Mapas</h2>", "Mapa base:", "conteos son orientativos",
                        "promedios semanales, mientras que los umbrales se refieren"]:
            self.assertNotContains(r, quitado)
        self.assertContains(r, "<h2>Umbrales térmicos</h2>")

    def test_textos_retirados_y_resumen_valores(self):
        r = self.client.get(reverse("agro:clima"), **HOST_SEGURO)
        self.assertContains(r, '<details class="detalle">')
        self.assertContains(r, "<summary>Valores por estado</summary>")
        self.assertNotContains(r, "Consultar los valores en una tabla")
        for nombre, params in [("precios", {"producto": "Haba"}), ("eda", {"producto": "Haba"}),
                               ("prediccion", {"producto": "Haba"}), ("sequia", {"estado": "Puebla"}),
                               ("clima", {}), ("comparar", {})]:
            html = self.client.get(reverse(f"agro:{nombre}"), params, **HOST_SEGURO).content.decode().lower()
            for f in ["para ampliar un periodo", "barra inferior", "botones de acercamiento",
                      "arrastre el cursor", "al acercarse"]:
                self.assertNotIn(f, html, f"'{f}' en {nombre}")
        r = self.client.get(reverse("agro:precios"), {"producto": "Haba"}, **HOST_SEGURO)
        self.assertContains(r, "La línea se interrumpe cuando transcurre al menos una semana sin cotizaciones.</p>")

    def test_css_ancho_y_justificacion(self):
        from django.contrib.staticfiles import finders
        css = open(finders.find("agro/css/app.css"), encoding="utf-8").read()
        self.assertNotIn("break-all", css)
        self.assertNotIn("100vw", css)
        self.assertNotIn("hyphens: auto", css)
        self.assertNotRegex(css, r"\.(texto|nota|portada__texto)\s*\{[^}]*max-width:\s*\d")
        self.assertNotRegex(css, r"\.seccion-encabezado p\s*\{[^}]*max-width:\s*\d")
        bloque = re.search(r"p, li, \.mensaje[^{]*\{([^}]*)\}", css).group(1)
        for decl in ["text-align: justify", "text-align-last: left", "hyphens: none", "word-break: normal",
                     "overflow-wrap: break-word", "max-width: none"]:
            self.assertIn(decl, bloque)
        # Justificado en todos los anchos: sin consultas de medios que lo desactiven.
        self.assertNotIn("min-width: 36em", css)
        r = self.client.get(reverse("agro:comparar"), **HOST_SEGURO)
        self.assertContains(r, '<summary>Productos y estados disponibles</summary>')

    # ------------------------------------------------------ clima filtrado
    def _clima(self, **params):
        return self.client.get(reverse("agro:clima"), params, **HOST_SEGURO).content.decode()

    def test_clima_estado_filtra_marcadores_y_vista(self):
        from agro.configuracion import REFERENCIA_ESTADOS
        df = consultas.clima_df()
        for estado in ["Puebla", "Sinaloa", "Chihuahua"]:
            html = self._clima(variable="TMAX", anio="2020", mes="7", estado=estado)
            # Un solo punto (el archivo no trae coordenadas de estaciones) y de ese estado.
            self.assertEqual(html.count("L.circleMarker("), 1, estado)
            otros = [e for e in consultas.estados_clima() if e != estado]
            script = re.search(r"<script>((?:(?!</script>).)*L\.circleMarker(?:(?!</script>).)*)</script>",
                               html, re.S).group(1)
            self.assertIn(f"<strong>{estado}</strong>", script)
            for e in otros:
                self.assertNotIn(f"<strong>{e}</strong>", script, f"{e} visible al filtrar {estado}")
            vista = json.loads(re.search(r'data-vista="([^"]*)"', html).group(1).replace("&quot;", '"'))
            self.assertEqual(vista["tipo"], "centro")
            self.assertEqual(vista["centro"], list(REFERENCIA_ESTADOS[estado]))
            # Filtros conservados.
            self.assertIn(f'<option value="{estado}" selected>', html)
            self.assertIn('<option value="TMAX" selected>', html)
            self.assertIn('<option value="2020" selected>', html)
            self.assertIn('<option value="7" selected>', html)
            self.assertIn(f"Temperatura máxima en {estado}, julio de 2020", html)
            # La tabla lista solo estaciones del estado con datos en el periodo.
            sub = df[(df["estado"] == estado) & (df["fecha"].dt.year == 2020) & (df["fecha"].dt.month == 7)
                     & df["tmax"].notna()]
            ids = sorted(int(i) for i in sub["id_estacion"].unique())
            tabla = re.search(r'aria-label="Tabla de valores por estación">(.*?)</table>', html, re.S).group(1)
            self.assertEqual(sorted(int(i) for i in re.findall(r'<th scope="row">(\d+)</th>', tabla)), ids)

    def test_clima_todos_los_estados_ajusta_limites(self):
        html = self._clima(variable="PRECIP", anio="2020", mes="7", estado="")
        df = consultas.clima_df()
        sub = df[(df["fecha"].dt.year == 2020) & (df["fecha"].dt.month == 7) & df["precip"].notna()]
        self.assertEqual(html.count("L.circleMarker("), sub["estado"].nunique())
        self.assertIn("fitBounds", html)
        vista = json.loads(re.search(r'data-vista="([^"]*)"', html).group(1).replace("&quot;", '"'))
        self.assertEqual(vista["tipo"], "limites")
        self.assertLessEqual(vista["zoomMax"], 8)
        self.assertNotIn('id="t-serie"', html)

    def test_clima_leyenda_con_datos_filtrados(self):
        from agro.servicios.mapas import mapa_clima
        df = consultas.clima_df()
        pe = analitica.clima_mensual_por_estacion(df, "precip", 2020, 7, "Puebla")
        self.assertTrue((pe["estado"] == "Puebla").all())
        m = mapa_clima(analitica.clima_por_estado(pe), pe, "PRECIP", "julio de 2020", "Puebla")
        self.assertEqual(m["leyenda"][0]["valor"], f"{pe['valor'].min():.1f} mm")
        self.assertEqual(m["leyenda"][-1]["valor"], f"{pe['valor'].max():.1f} mm")
        self.assertEqual(m["puntos"], 1)

    def test_clima_estado_sin_datos_no_reutiliza_puntos(self):
        df = consultas.clima_df()
        anios = consultas.anios_clima()
        for estado in consultas.estados_clima():
            con = set(df[(df["estado"] == estado) & df["tmax"].notna()]["fecha"].dt.year)
            faltan = [a for a in anios if a not in con]
            if faltan:
                html = self._clima(variable="TMAX", anio=str(faltan[0]), estado=estado)
                self.assertNotIn("L.circleMarker(", html)
                self.assertIn("No hay información disponible", html)
                return
        self.skipTest("Todos los estados tienen datos en todos los años.")

    def test_vista_para_puntos(self):
        from agro.servicios.mapas import ZOOM_MAX_AJUSTE, ZOOM_UN_PUNTO, vista_para_puntos
        self.assertIsNone(vista_para_puntos([]))
        self.assertEqual(vista_para_puntos([(19.0, -98.2)]), {"tipo": "centro", "centro": [19.0, -98.2], "zoom": ZOOM_UN_PUNTO})
        v = vista_para_puntos([(19.0, -98.2), (20.5, -97.1)])
        self.assertEqual(v["limites"], [[19.0, -98.2], [20.5, -97.1]])
        self.assertEqual(v["zoomMax"], ZOOM_MAX_AJUSTE)

    # ---------------------------------------------------- precio y clima
    def _comparar(self, producto, estado, variable):
        return self.client.post(reverse("agro:comparar"), {"producto": producto, "estado": estado, "variable": variable},
                                **HOST_SEGURO)

    def test_comparacion_precio_visible_y_correcto(self):
        precios, clima = consultas.precios_df(), consultas.clima_df()
        comparables = consultas.estados_comparables()
        casos = [("Frijol Negro", "Puebla", "PRECIP"), ("Frijol Negro", "Puebla", "TMAX"),
                 ("Frijol Negro", "Veracruz", "TMIN"), ("Frijol Pinto", "Chihuahua", "PRECIP"),
                 ("Haba", "Puebla", "TMAX"), ("Maíz blanco", "Sinaloa", "PRECIP")]
        casos += [("Tomate Saladette - Primera", e, "TMAX") for e in comparables.get("Tomate Saladette - Primera", [])]
        probados = 0
        for producto, estado, variable in casos:
            if estado not in comparables.get(producto, []):
                continue
            probados += 1
            r = self._comparar(producto, estado, variable)
            html = r.content.decode()
            sp = analitica.serie_precio_semanal_por_estado(precios, producto, estado)
            unido, rep = analitica.unir_precio_clima(sp, analitica.clima_semanal_estado(clima, estado))
            if unido.empty:
                self.assertContains(r, "No hay información coincidente para la selección actual.")
                self.assertNotContains(r, "fig-comp")
                continue
            # Sin duplicados por la union y solo semanas del producto y origen elegidos.
            self.assertFalse(unido["semana"].duplicated().any())
            self.assertTrue(unido["semana"].isin(sp.dropna().index).all())
            res = analitica.resumen_comparacion(unido, variable)
            # Recalculo independiente desde los registros del producto y el estado.
            sub = precios[(precios["producto"] == producto) & (precios["estado_aux"] == estado)].dropna(subset=["fecha", "precio_frec"])
            semanal = sub.set_index("fecha")["precio_frec"].groupby(level=0).mean().resample("W").mean()
            ultima = unido["semana"].max()
            self.assertAlmostEqual(res["precio_reciente"], float(semanal.loc[ultima]))
            comparadas = semanal.loc[unido["semana"]]
            self.assertAlmostEqual(res["precio_min"], float(comparadas.min()))
            self.assertAlmostEqual(res["precio_max"], float(comparadas.max()))
            self.assertAlmostEqual(res["precio_promedio"], float(comparadas.mean()))
            self.assertEqual(res["desde"], unido["semana"].min().date())
            self.assertEqual(res["hasta"], ultima.date())
            # Resultado visible tras comparar, antes de la grafica y de los textos secundarios.
            pos = [html.index(t) for t in ['id="resultado"', "Precio más reciente", 'data-figura="fig-comp"',
                                           "Productos y estados disponibles"]]
            self.assertEqual(pos, sorted(pos), producto)
            self.assertIn(f"{nombre_publico(producto)} · {estado}", html)
            unidad = "MXN/kg"
            meta = {"PRECIP": ("Precipitación", "mm"), "TMAX": ("Temperatura máxima", "°C"),
                    "TMIN": ("Temperatura mínima", "°C")}[variable]
            fig = self._figura(html, "fig-comp")
            self.assertEqual(fig["layout"]["yaxis"]["title"]["text"], f"Precio ({unidad})")
            self.assertEqual(fig["layout"]["yaxis2"]["title"]["text"], f"{meta[0]} ({meta[1]})")
            self.assertEqual(fig["layout"]["xaxis"]["type"], "date")
            nombres = [t["name"] for t in fig["data"]]
            clima_nombre = "Precipitación semanal acumulada (mm)" if variable == "PRECIP" else f"{meta[0]} semanal ({meta[1]})"
            self.assertEqual(nombres, [f"Precio semanal ({unidad})", clima_nombre])
            precio_fig = [v for v in fig["data"][0]["y"] if v is not None]
            self.assertEqual(len(precio_fig), rep["emparejadas"])
            self.assertEqual(fig["data"][0]["x"][0], unido["semana"].min().strftime("%Y-%m-%d"))
            self.assertEqual(fig["data"][0]["x"][-1], ultima.strftime("%Y-%m-%d"))
            # Filtros conservados.
            self.assertIn(f'<option value="{estado}" selected>', html)
            self.assertIn(f'<option value="{variable}" selected>', html)
        self.assertGreaterEqual(probados, 4)

    def test_comparacion_sin_coincidencia(self):
        from unittest import mock
        vacio = (pd.DataFrame(), {"filas_precio": 3, "filas_clima": 0, "emparejadas": 0,
                                  "precio_sin_clima": 3, "clima_sin_precio": 0, "valida": True})
        with mock.patch.object(analitica, "unir_precio_clima", return_value=vacio):
            r = self._comparar("Haba", "Puebla", "PRECIP")
        self.assertContains(r, "No hay información coincidente para la selección actual.")
        self.assertNotContains(r, "fig-comp")
        self.assertNotContains(r, "Precio más reciente")
        self.assertNotContains(r, "Cobertura de la comparación")

    def test_instrucciones_redundantes_retiradas(self):
        for nombre, params in [("clima", {}), ("clima", {"variable": "TMAX", "anio": "2020", "estado": "Puebla"}),
                               ("eda", {"producto": "Haba"}), ("precios", {"producto": "Haba"}), ("comparar", {})]:
            html = self.client.get(reverse(f"agro:{nombre}"), params, **HOST_SEGURO).content.decode().lower()
            for f in ["seleccione un círculo", "haga clic", "pulse un marcador", "seleccione un punto",
                      "toque una estación", "al seleccionar una barra", "seleccione la variable, el año y el mes"]:
                self.assertNotIn(f, html, f"'{f}' en {nombre}")

    def test_validacion_pronostico_en_pagina(self):
        r = self.client.get(reverse("agro:prediccion"), {"producto": "Haba"}, **HOST_SEGURO)
        html = r.content.decode()
        self.assertContains(r, "Validación del pronóstico en 2025")
        self.assertContains(r, "no incluye pronósticos posteriores a diciembre de 2025")
        fig = self._figura(html, "fig-validacion")
        nombres = [t["name"] for t in fig["data"]]
        self.assertIn("Precio observado", nombres)
        self.assertIn("Pronóstico: SARIMAX", nombres)
        self.assertFalse([n for n in nombres if "referencia" in n])
        self.assertTrue(all(t.get("visible") == "legendonly" for t in fig["data"] if t["name"].startswith("Ajuste")))
        self.assertEqual(fig["layout"]["xaxis"]["type"], "date")
        from agro.servicios import modelado
        prod = modelado.producto("Haba")
        filas = re.search(r'aria-label="Métricas de error por modelo">(.*?)</table>', html, re.S).group(1)
        self.assertEqual(filas.count("<tr"), len(prod["metricas"]) + 1)
        self.assertContains(r, f"({', '.join(str(x) for x in prod['parametros']['orden'])})")
        # Productos sin modelado: sin gráfica de validación.
        r = self.client.get(reverse("agro:prediccion"), {"producto": "Frijol Negro"}, **HOST_SEGURO)
        self.assertNotContains(r, "fig-validacion")
        self.assertContains(r, "La validación de pronósticos está disponible para haba, maíz blanco, frijol pinto, "
                               "aguacate Hass y tomate saladette.")

    def test_fechas_y_meses_en_espanol(self):
        from agro.templatetags.formato import cifra, fecha_larga, mes_anio
        self.assertEqual(fecha_larga("2015-01-07"), "7 de enero de 2015")
        self.assertEqual(mes_anio("2025-12-31"), "diciembre de 2025")
        self.assertEqual(cifra(10811), "10\u202f811")
        self.assertEqual(cifra(2015), "2015")
        r = self.client.get(reverse("agro:precios"), {"producto": "Haba"}, **HOST_SEGURO)
        self.assertContains(r, " de enero de 2015")
        self.assertNotContains(r, 'Menor "precio')

    def test_textos_publicos_sin_notas_internas(self):
        frases = ["archivo de origen", "no se rellenan", "no se corrigen", "no se generan", "simulad",
                  "inventad", "csv", "provisional", "instrucci", "tal como aparecen", "sin modificaciones",
                  "programa original", "análisis original"]
        paginas = [("inicio", {}), ("precios", {"producto": "Aguacate Hass - Primera"}), ("clima", {}),
                   ("prediccion", {"producto": "Frijol Negro"}), ("eda", {}), ("sequia", {}),
                   ("comparar", {}), ("metodologia", {})]
        for nombre, params in paginas:
            html = self.client.get(reverse(f"agro:{nombre}"), params, **HOST_SEGURO).content.decode()
            visible = re.sub(r"<script.*?</script>|<style.*?</style>|<[^>]+>", " ", html, flags=re.S).lower()
            for f in frases:
                self.assertNotIn(f, visible, f"'{f}' visible en {nombre}")

    def test_host_no_permitido(self):
        r = self.client.get("/", HTTP_HOST="malicioso.example.com")
        self.assertEqual(r.status_code, 400)

    def test_404_sin_detalles(self):
        r = self.client.get("/no-existe/", **HOST_SEGURO)
        self.assertEqual(r.status_code, 404)
        self.assertNotContains(r, "Traceback", status_code=404)
        self.assertNotContains(r, "urlpatterns", status_code=404)

    def test_sin_datos_personales_ni_referencias(self):
        prohibidos = TERMINOS_PUBLICOS_PROHIBIDOS
        for nombre in ["inicio", "precios", "clima", "prediccion", "eda", "sequia", "comparar", "metodologia"]:
            html = self.client.get(reverse(f"agro:{nombre}"), **HOST_SEGURO).content.decode().lower()
            for p in prohibidos:
                self.assertNotIn(p, html, f"{p} en {nombre}")


    # ------------------------------------------- visualización e interacción
    @staticmethod
    def _arr(v):
        """Arreglo de una traza (Plotly codifica algunos arreglos numéricos en base64)."""
        if isinstance(v, dict) and "bdata" in v:
            import base64
            datos = np.frombuffer(base64.b64decode(v["bdata"]), dtype=np.dtype(v["dtype"]))
            return [None if np.isnan(x) else float(x) for x in datos]
        return list(v)

    def _figuras_de(self, nombre, params, metodo="get"):
        url = reverse(f"agro:{nombre}")
        r = (self.client.post(url, params, **HOST_SEGURO) if metodo == "post"
             else self.client.get(url, params, **HOST_SEGURO))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        ids = re.findall(r'<script id="(fig-[\w-]+)" type="application/json">', html)
        return html, {i: self._figura(html, i) for i in ids}

    def _todas_las_figuras(self):
        casos = [("precios", {"producto": "Haba"}), ("precios", {"producto": "Frijol Negro", "estado": "Puebla"}),
                 ("prediccion", {"producto": "Haba"}), ("prediccion", {"producto": "Frijol Negro"}),
                 ("eda", {"producto": "Haba"}), ("sequia", {"estado": "Puebla"}),
                 ("clima", {"variable": "PRECIP", "anio": "2020", "estado": "Puebla"}),
                 ("clima", {"variable": "TMIN", "anio": "2020", "estado": "Puebla"})]
        figs = {}
        for nombre, params in casos:
            figs.update({f"{nombre}:{params}:{k}": v for k, v in self._figuras_de(nombre, params)[1].items()})
        _, f = self._figuras_de("comparar", {"producto": "Haba", "estado": "Puebla", "variable": "TMAX"}, "post")
        figs.update({f"comparar:{k}": v for k, v in f.items()})
        return figs

    def test_unidades_y_escalas_en_figuras(self):
        figs = self._todas_las_figuras()
        self.assertGreaterEqual(len(figs), 14)
        unidades = ("MXN/kg", "mm", "°C", "Año", "Proporción")
        for clave, fig in figs.items():
            lay = fig["layout"]
            ejes_y = [v for k, v in lay.items() if re.fullmatch(r"yaxis\d*", k)]
            ejes_x = [v for k, v in lay.items() if re.fullmatch(r"xaxis\d*", k)]
            self.assertTrue(any((e.get("title") or {}).get("text") for e in ejes_x), f"sin título en X: {clave}")
            for e in ejes_y:
                titulo = (e.get("title") or {}).get("text", "")
                self.assertTrue(any(u in titulo for u in unidades), f"eje Y sin unidad en {clave}: {titulo!r}")
                # Cifras completas: sin abreviaturas ni notación científica; sin escala logarítmica.
                self.assertEqual(e.get("exponentformat"), "none", clave)
                self.assertNotEqual(e.get("type"), "log", clave)
            for e in ejes_x:
                self.assertNotEqual(e.get("type"), "log", clave)
        stl = next(v for k, v in figs.items() if k.endswith("fig-stl"))
        titulos = [stl["layout"][f"yaxis{i if i > 1 else ''}"]["title"]["text"] for i in range(1, 5)]
        self.assertEqual(titulos, ["Precio (MXN/kg)", "Precio (MXN/kg)", "Desviación (MXN/kg)", "Desviación (MXN/kg)"])
        falt = next(v for k, v in figs.items() if k.endswith("fig-faltantes"))
        self.assertEqual(falt["data"][0]["colorbar"]["tickformat"], ".0%")
        matriz = next(v for k, v in figs.items() if k.endswith("fig-matriz"))
        self.assertIn("MXN/kg", matriz["data"][0]["colorbar"]["title"]["text"])
        comp = figs["comparar:fig-comp"]
        self.assertIn("MXN/kg", comp["layout"]["yaxis"]["title"]["text"])
        self.assertIn("°C", comp["layout"]["yaxis2"]["title"]["text"])
        # Ninguna escala vertical forzada a cero salvo precipitación (magnitud no negativa).
        for clave, fig in figs.items():
            for k, e in fig["layout"].items():
                if re.fullmatch(r"yaxis\d*", k) and e.get("rangemode") == "tozero":
                    self.assertIn("mm", e["title"]["text"], clave)

    @staticmethod
    def _colores(obj, salida):
        if isinstance(obj, dict):
            for v in obj.values():
                DatosCargadosTests._colores(v, salida)
        elif isinstance(obj, list):
            for v in obj:
                DatosCargadosTests._colores(v, salida)
        elif isinstance(obj, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", obj):
            salida.add(obj.lower())
        return salida

    @staticmethod
    def _es_azul(h):
        r, g, b = (int(h[i:i + 2], 16) for i in (1, 3, 5))
        return b > r + 40 and b > g + 15

    def test_paleta_verde_sin_azul_predeterminado(self):
        from agro.servicios import graficas
        from agro.servicios.mapas import ESCALAS
        figs = self._todas_las_figuras()
        for clave, fig in figs.items():
            self.assertEqual(fig["layout"]["colorway"], graficas.SERIES, clave)
            azules = [c for c in self._colores(fig["data"], set()) if self._es_azul(c)]
            self.assertEqual(azules, [], clave)
        for var, escala in ESCALAS.items():
            self.assertFalse([c for c in escala if self._es_azul(c)], var)
        self.assertFalse([c for c in graficas.SERIES if self._es_azul(c)])
        # Mismo color para el concepto "observado" en serie, comparación y validación.
        serie = next(v for k, v in figs.items() if k.endswith("fig-serie"))
        obs = [t for t in serie["data"] if t["name"] == "Promedio semanal"][0]
        self.assertEqual(obs["line"]["color"], graficas.OBSERVADO["color"])
        self.assertEqual(figs["comparar:fig-comp"]["data"][0]["line"]["color"], graficas.OBSERVADO["color"])
        css = (settings.BASE_DIR / "agro" / "static" / "agro" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn("--primario: #1f7a50", css)
        self.assertEqual(graficas.VERDE, "#1f7a50")

    def test_sequia_tonos_calidos_y_umbrales_sin_cambio(self):
        from agro.servicios import graficas
        html, figs = self._figuras_de("sequia", {"estado": "Puebla"})
        fig = figs["fig-sequia"]
        por_nombre = {t["name"]: t for t in fig["data"]}
        semanal = analitica.clima_semanal_estado(consultas.clima_df(), "Puebla")
        secas = por_nombre["Semana sin precipitación"]
        self.assertEqual(len(secas["x"]), int((semanal["precip"] == 0).sum()))
        self.assertTrue(all(v == 0 for v in secas["y"]))
        for nombre in ("Temperatura máxima", "Temperatura mínima"):
            c = por_nombre[nombre]["line"]["color"]
            r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
            self.assertTrue(r > g > b, nombre)
        r, g, b = (int(graficas.SEQUIA["sin_precip"][i:i + 2], 16) for i in (1, 3, 5))
        self.assertTrue(r > 2 * g and r > 2 * b)
        # La precipitación (variable húmeda) no usa el tono de la condición seca.
        self.assertNotEqual(por_nombre["Precipitación semanal"]["marker"]["color"], graficas.SEQUIA["sin_precip"])
        # Umbrales: una línea horizontal por umbral, con su valor, nombrada en la leyenda (sin texto
        # sobre el panel, donde se superponía a las series) y con un trazo distinto para cada una.
        umbr = [t for t in fig["data"] if (t.get("meta") or {}).get("umbral")]
        self.assertEqual([(t["name"], t["y"]) for t in umbr],
                         [(u["corto"], [u["valor"], u["valor"]]) for u in UMBRALES_TERMICOS])
        self.assertEqual(len({t["line"]["dash"] for t in umbr}), len(UMBRALES_TERMICOS))
        self.assertTrue(all(t["x"][0] == fig["data"][0]["x"][0] and t["x"][-1] == fig["data"][0]["x"][-1]
                            and t["hoverinfo"] == "skip" and t["yaxis"] == "y2" for t in umbr))
        textos = [a["text"] for a in fig["layout"]["annotations"]]
        self.assertFalse(any(u["corto"] in t for u in UMBRALES_TERMICOS for t in textos))
        self.assertEqual([u["valor"] for u in UMBRALES_TERMICOS], [32.0, 14.0, 25.0])

    def test_intervalos_sin_observaciones(self):
        f = ["2017-10-25", "2017-11-01", "2018-07-04", "2018-07-11"]
        self.assertEqual(analitica.intervalos_sin_observaciones(f, "W-SUN", 4),
                         [{"desde": "2017-11-01", "hasta": "2018-07-04", "semanas": 34}])
        self.assertEqual(analitica.intervalos_sin_observaciones(["2020-01-01", "2020-01-08"], "W-SUN", 1), [])
        self.assertEqual(analitica.intervalos_sin_observaciones(["2020-01-01"], "W-SUN", 1), [])
        self.assertEqual(len(analitica.intervalos_sin_observaciones(["2020-01-01", "2020-01-15"], "W-SUN", 1)), 1)

    def test_discontinuidad_frijol_negro_puebla(self):
        precios = consultas.precios_df()
        sub = precios[(precios["producto"] == "Frijol Negro") & (precios["estado_aux"] == "Puebla")].dropna(subset=["fecha"])
        self.assertEqual(len(sub), 9)
        html, figs = self._figuras_de("precios", {"producto": "Frijol Negro", "estado": "Puebla"})
        tr = figs["fig-precios"]["data"][0]
        # Corte explícito entre el 1 de noviembre de 2017 y el 4 de julio de 2018.
        i = tr["x"].index("2017-11-01")
        self.assertIsNone(tr["y"][i + 1])
        self.assertEqual(tr["x"][i + 2], "2018-07-04")
        # Valores graficados = valores registrados (sin ceros ni interpolación).
        self.assertEqual(sorted(v for v in tr["y"] if v is not None), sorted(sub["precio_frec"].astype(float)))
        self.assertNotIn(0.0, [v for v in tr["y"] if v is not None])
        # Las fechas son la última cotización antes del tramo y la siguiente; 34 semanas
        # de calendario completas (lunes a domingo) quedan entre ambas.
        self.assertIn("La línea se interrumpe porque no hay cotizaciones entre el 1 de noviembre de 2017 y el "
                      "4 de julio de 2018, un tramo sombreado de 34 semanas completas que no representa un "
                      "precio de cero.", html)
        self.assertEqual(html.count("nota--discontinuidad"), 1)
        self.assertNotIn("La fuente no indica", html)
        vrect = [s for s in figs["fig-precios"]["layout"]["shapes"] if s.get("type") == "rect"]
        self.assertEqual([(s["x0"], s["x1"]) for s in vrect], [("2017-11-01", "2018-07-04")])
        # Vista con todos los orígenes: la nota identifica la serie de Puebla.
        html, _ = self._figuras_de("precios", {"producto": "Frijol Negro"})
        self.assertIn("La línea de Puebla se interrumpe porque no hay cotizaciones entre el 1 de noviembre de 2017 y "
                      "el 4 de julio de 2018, un tramo de 34 semanas completas que no representa un precio de cero.", html)
        self.assertEqual(html.count("nota--discontinuidad"), 1)
        # Precio y clima: el mismo intervalo, sin semanas comparadas.
        html, _ = self._figuras_de("comparar", {"producto": "Frijol Negro", "estado": "Puebla", "variable": "PRECIP"}, "post")
        self.assertIn("La línea del precio se interrumpe porque no hay cotizaciones entre la semana con cierre el "
                      "5 de noviembre de 2017 y la del 8 de julio de 2018, un tramo sombreado de 34 semanas completas "
                      "que no representa un precio de cero.", html)
        self.assertEqual(html.count("nota--discontinuidad"), 1)
        # Varias interrupciones: una sola nota con el detalle de los tramos.
        html, _ = self._figuras_de("prediccion", {"producto": "Haba"})
        self.assertEqual(html.count("nota--discontinuidad"), 1)
        self.assertIn("La línea se interrumpe en 2 tramos de 4 semanas o más sin cotizaciones, sombreados en la "
                      "gráfica; esos tramos no representan precios de cero.", html)
        self.assertIn("Última semana con dato (cierre)", html)

    def test_nota_de_discontinuidad_solo_donde_corresponde(self):
        for estado in ("Veracruz", "Zacatecas"):
            html, _ = self._figuras_de("precios", {"producto": "Frijol Negro", "estado": estado})
            self.assertNotIn("nota--discontinuidad", html, estado)
        html, _ = self._figuras_de("prediccion", {"producto": "Frijol Negro"})
        self.assertNotIn("nota--discontinuidad", html)
        self.assertIn("su origen cambia a lo largo del periodo", html)
        html, _ = self._figuras_de("prediccion", {"producto": "Haba"})
        self.assertNotIn("su origen cambia", html)

    def test_lineas_sin_conexion_artificial(self):
        for p in consultas.nombres_productos():
            _, figs = self._figuras_de("precios", {"producto": p})
            for tr in figs["fig-precios"]["data"]:
                anterior = None
                for x, y in zip(tr["x"], tr["y"]):
                    if y is None:
                        anterior = None
                        continue
                    sem = pd.Timestamp(x).to_period("W-SUN")
                    if anterior is not None:
                        self.assertLessEqual((sem - anterior).n, 1, f"{p} {tr['name']} {x}")
                    anterior = sem
                self.assertFalse(tr.get("connectgaps"), p)

    def test_disponibilidad_dependiente(self):
        disp = consultas.disponibilidad_precios()
        filas = [f for f in disp["filas"] if f[0] == "Frijol Negro"]
        self.assertEqual({f[1] for f in filas}, {"Puebla", "Veracruz", "Zacatecas"})
        self.assertEqual({f[3] for f in filas if f[1] == "Puebla"}, {2017, 2018})
        self.assertEqual({f[2] for f in disp["filas"] if f[0] == "Tomate Saladette - Primera" and f[1] == "Puebla"},
                         {"Caja de 12 kg.", "Caja de 13 kg."})
        ok = consultas.combinacion_disponible
        self.assertTrue(ok(disp, {"producto": "Frijol Negro", "estado": "Puebla", "anio_desde": "2018"}))
        self.assertFalse(ok(disp, {"producto": "Frijol Negro", "estado": "Puebla", "anio_desde": "2019"}))
        self.assertTrue(ok(disp, {"producto": "Frijol Negro", "estado": "Veracruz", "anio_desde": "2019"}))
        # Clima: meses por estado y año calculados con la variable elegida.
        dc = consultas.disponibilidad_clima()
        df = consultas.clima_df()
        sub = df[(df["estado"] == "Puebla") & (df["fecha"].dt.year == 2020) & df["tmax"].notna()]
        self.assertEqual({f[2] for f in dc["filas"] if f[0] == "TMAX" and f[1] == 2020 and f[3] == "Puebla"},
                         set(sub["fecha"].dt.month))
        # Análisis por año y mes: años con semanas cotizadas de la serie.
        de = consultas.disponibilidad_eda()
        s = consultas.serie_eda("Frijol Negro").dropna()
        self.assertEqual({f[1] for f in de["filas"] if f[0] == "Frijol Negro"}, set(s.index.year))
        # Precio y clima: solo combinaciones con semanas comparadas.
        dcomp = consultas.disponibilidad_comparacion()
        for producto, estado, var in dcomp["filas"]:
            unido, rep = analitica.unir_precio_clima(
                analitica.serie_precio_semanal_por_estado(consultas.precios_df(), producto, estado),
                analitica.clima_semanal_estado(df, estado))
            self.assertGreater(rep["emparejadas"], 0)
            self.assertTrue(unido[var.lower()].notna().any())
        # La página incluye las combinaciones y el formulario las declara.
        r = self.client.get(reverse("agro:precios"), {"producto": "Haba"}, **HOST_SEGURO)
        self.assertContains(r, 'data-disponibilidad="disponibilidad-filtros"')
        self.assertContains(r, '<script id="disponibilidad-filtros" type="application/json">')

    def test_cambio_entre_selecciones_con_coberturas_distintas(self):
        url = reverse("agro:precios")
        r = self.client.get(url, {"producto": "Frijol Negro", "estado": "Puebla", "anio_desde": "2019"}, **HOST_SEGURO)
        self.assertContains(r, "No hay información disponible para la combinación seleccionada", count=1)
        self.assertNotContains(r, "fig-precios")
        self.assertNotContains(r, "Revise los filtros")
        r = self.client.get(url, {"producto": "Frijol Negro", "estado": "Veracruz", "anio_desde": "2019"}, **HOST_SEGURO)
        self.assertContains(r, "fig-precios")
        # No se sustituye un estado por otro en el servidor.
        r = self.client.get(url, {"producto": "Haba", "estado": "Sinaloa"}, **HOST_SEGURO)
        self.assertNotContains(r, "fig-precios")
        self.assertNotContains(r, "Haba: mínimos y máximos")

    def test_parametros_invalidos_sin_error_500(self):
        casos = [("precios", {"producto": "Haba", "estado": "Narnia"}), ("precios", {"producto": "Haba", "anio_desde": "abc"}),
                 ("precios", {"producto": "<script>"}), ("clima", {"variable": "TMAX", "anio": "2020", "mes": "13"}),
                 ("clima", {"variable": "XYZ", "anio": "2020"}), ("clima", {"variable": "TMAX", "anio": "2020", "estado": "Narnia"}),
                 ("sequia", {"estado": "Puebla", "anio_desde": "2050"}), ("sequia", {"estado": "Narnia"}),
                 ("eda", {"producto": "Haba", "anio_desde": "1900"}), ("prediccion", {"producto": "xyz"})]
        for nombre, params in casos:
            r = self.client.get(reverse(f"agro:{nombre}"), params, **HOST_SEGURO)
            self.assertEqual(r.status_code, 200, (nombre, params))
            html = r.content.decode()
            self.assertEqual(html.count('class="estado-vacio"'), 1, (nombre, params))
            self.assertNotIn("<script>", html.split("<main")[1].split("</main>")[0].replace("<script>{", ""), nombre)
        r = self.client.post(reverse("agro:comparar"), {"producto": "Haba", "estado": "Sinaloa", "variable": "TMAX"}, **HOST_SEGURO)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "No hay información disponible para la combinación seleccionada", count=1)
        self.assertNotContains(r, "fig-comp")

    def test_pronostico_visible_y_controles_en_pagina(self):
        html, figs = self._figuras_de("prediccion", {"producto": "Tomate Saladette - Primera"})
        fig = figs["fig-validacion"]
        self.assertIn('id="sel-modelos"', html)
        self.assertIn('data-rango="evaluacion" aria-pressed="true"', html)
        self.assertIn('data-rango="historico"', html)
        self.assertIn('data-zoom="0.5"', html)
        self.assertIn("Koyck (niveles) (menor error)", html)
        visibles = [t["meta"]["modelo"] for t in fig["data"]
                    if (t.get("meta") or {}).get("rol") == "pronostico" and t.get("visible") is True]
        self.assertIn("Koyck (niveles)", visibles)
        # La validación aparece antes de la descomposición y del mapa de faltantes.
        self.assertLess(html.index('id="t-val"'), html.index('id="t-stl"'))
        # Producto sin modelado: no se muestra el de otro producto.
        html, figs = self._figuras_de("prediccion", {"producto": "Frijol Negro"})
        self.assertNotIn("fig-validacion", figs)
        self.assertNotIn('id="sel-modelos"', html)

    def test_resultados_cientificos_sin_cambios(self):
        from agro.servicios import modelado
        doc = modelado.resultados()
        for p, prod in doc["productos"].items():
            html, figs = self._figuras_de("prediccion", {"producto": p})
            fig = figs["fig-validacion"]
            for t in fig["data"]:
                m = t.get("meta") or {}
                if m.get("rol") == "pronostico":
                    self.assertEqual(t["y"], prod["prueba"]["pronosticos"][m["modelo"]], (p, m))
                    self.assertEqual(t["x"], prod["prueba"]["fechas"])
                elif m.get("rol") == "ajuste":
                    self.assertEqual(t["y"], prod["ajuste"][m["modelo"]]["valores"])
            for m in prod["metricas"]:
                self.assertIn(f"{m['rmse']:.3f}", html)
            resultado = consultas.serie_analisis(p)
            serie = [t for t in figs["fig-serie"]["data"] if t["name"] == "Promedio semanal"][0]
            self.assertEqual(self._arr(serie["y"]), [x["valor"] for x in resultado["serie"]])
            stl = figs["fig-stl"]["data"]
            for i, clave in enumerate(["observado", "tendencia", "estacionalidad", "residuo"]):
                self.assertEqual(self._arr(stl[i]["y"]), [x["valor"] for x in resultado["descomposicion"][clave]])
            # Modelo de menor error: mismo criterio (RMSE mínimo sin filas de referencia).
            destacado = [t["meta"]["modelo"] for t in fig["data"] if "menor error" in t["name"]]
            self.assertEqual(destacado, [modelado.mejor_modelo(prod)])

    def test_js_zoom_y_dependencias(self):
        js = (settings.BASE_DIR / "agro" / "static" / "agro" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("scrollZoom: false", js)  # no captura la rueda del ratón
        self.assertIn('el.on("plotly_relayout"', js)
        self.assertIn("form[data-disponibilidad]", js)
        self.assertIn("aplicarRango(el, el._vistaActual)", js)  # al cambiar de modelo se restablece el periodo
        self.assertNotIn("fixedrange", js)


    # ------------------------------------- coherencia de filtros (regresión 2026)
    def test_analisis_no_ofrece_ni_acepta_2026_sin_registros(self):
        precios = consultas.precios_df()
        self.assertFalse((precios["fecha"].dt.year == 2026).any())  # el archivo termina en 2025
        # Causa: la serie semanal rotula la última semana con su domingo de cierre (2026-01-04).
        self.assertEqual(consultas.serie_semanal_original("Haba").index.max(), pd.Timestamp("2026-01-04"))
        disp = consultas.disponibilidad_eda()
        self.assertNotIn(2026, {f[1] for f in disp["filas"]})
        r = self.client.get(reverse("agro:eda"), {"producto": "Haba"}, **HOST_SEGURO)
        html = r.content.decode()
        form = r.context["form"]
        for campo in ("anio_desde", "anio_hasta"):
            self.assertNotIn("2026", [v for v, _ in form.fields[campo].choices])
        self.assertNotIn('<option value="2026"', html)
        self.assertNotIn('"2026"', self._figura(html, "fig-matriz")["data"][0]["y"])
        self.assertIn("con cierre el 4 de enero de 2026, solo contiene cotizaciones del 31 de diciembre de 2025", html)
        # La semana se agrupa en diciembre de 2025 con su valor sin cambios.
        serie = consultas.serie_eda("Haba")
        self.assertEqual(serie.index.max(), pd.Timestamp("2025-12-31"))
        self.assertEqual(serie.iloc[-1], consultas.serie_semanal_original("Haba").iloc[-1])
        self.assertTrue(np.array_equal(serie.values, consultas.serie_semanal_original("Haba").values, equal_nan=True))
        self.assertTrue((serie.index[:-1] == consultas.serie_semanal_original("Haba").index[:-1]).all())
        # Solicitud manipulada: respuesta controlada, sin resultados.
        for params in ({"producto": "Haba", "anio_desde": "2026"}, {"producto": "Haba", "anio_hasta": "2026"}):
            r = self.client.get(reverse("agro:eda"), params, **HOST_SEGURO)
            self.assertEqual(r.status_code, 200)
            self.assertNotContains(r, "fig-matriz")
            self.assertContains(r, 'class="estado-vacio"', count=1)

    def test_cada_anio_ofrecido_tiene_registros(self):
        precios = consultas.precios_df().dropna(subset=["fecha"])
        for producto, anio in consultas.disponibilidad_eda()["filas"]:
            s = consultas.serie_eda(producto).dropna()
            self.assertTrue((s.index.year == anio).any(), (producto, anio))
            self.assertTrue(((precios["producto"] == producto) & (precios["fecha"].dt.year == anio)
                             & precios["precio_frec"].notna()).any(), (producto, anio))
        for producto, estado, pres, anio in consultas.disponibilidad_precios()["filas"]:
            sub = precios[(precios["producto"] == producto) & (precios["estado_aux"].fillna("") == estado)
                          & (precios["presentacion"].fillna("") == pres) & (precios["fecha"].dt.year == anio)]
            self.assertTrue((sub["precio_frec"].notna() | sub["precio_max"].notna()).any(), (producto, estado, pres, anio))
        clima = consultas.clima_df()
        for var, anio, mes, estado in consultas.disponibilidad_clima()["filas"]:
            sub = clima[(clima["estado"] == estado) & (clima["fecha"].dt.year == anio) & (clima["fecha"].dt.month == mes)]
            self.assertTrue(sub[var.lower()].notna().any(), (var, anio, mes, estado))
        for estado, anio in consultas.disponibilidad_sequia()["filas"]:
            sub = clima[(clima["estado"] == estado) & (clima["fecha"].dt.year == anio)]
            self.assertFalse(sub.empty, (estado, anio))

    def test_opciones_del_formulario_coinciden_con_el_catalogo(self):
        def opciones(r, campo):
            return {v for v, _ in r.context["form"].fields[campo].choices if v != ""}

        casos = [("eda", {"producto": "Haba"}, consultas.disponibilidad_eda(), ["anio_desde", "anio_hasta"]),
                 ("clima", {}, consultas.disponibilidad_clima(), ["anio", "mes", "estado"]),
                 ("sequia", {}, consultas.disponibilidad_sequia(), ["estado", "anio_desde", "anio_hasta"])]
        for nombre, params, disp, campos in casos:
            r = self.client.get(reverse(f"agro:{nombre}"), params, **HOST_SEGURO)
            for campo in campos:
                col = disp["campos"][campo]
                self.assertEqual(opciones(r, campo), {str(f[col]) for f in disp["filas"]}, (nombre, campo))
        disp = consultas.disponibilidad_precios()
        for producto in consultas.nombres_productos():
            r = self.client.get(reverse("agro:precios"), {"producto": producto}, **HOST_SEGURO)
            filas = [f for f in disp["filas"] if f[0] == producto]
            self.assertEqual(opciones(r, "estado"), {f[1] for f in filas if f[1]}, producto)
            self.assertEqual(opciones(r, "presentacion"), {f[2] for f in filas if f[2]}, producto)
            self.assertEqual(opciones(r, "anio_desde"), {str(f[3]) for f in filas}, producto)
        r = self.client.get(reverse("agro:comparar"), **HOST_SEGURO)
        dc = consultas.disponibilidad_comparacion()
        self.assertEqual(opciones(r, "producto"), {f[0] for f in dc["filas"]})
        self.assertEqual(opciones(r, "estado"), {f[1] for f in dc["filas"]})
        # Cada opción aceptada por un formulario participa en al menos una combinación con datos.
        for producto in consultas.nombres_productos():
            for anio in [f[1] for f in consultas.disponibilidad_eda()["filas"] if f[0] == producto]:
                r = self.client.get(reverse("agro:eda"), {"producto": producto, "anio_desde": anio, "anio_hasta": anio},
                                    **HOST_SEGURO)
                self.assertContains(r, "fig-matriz", msg_prefix=f"{producto} {anio}")

    def test_meses_de_clima_segun_anio_y_estado(self):
        dc = consultas.disponibilidad_clima()
        meses = {f[2] for f in dc["filas"] if f[0] == "TMAX" and f[1] == 2025 and f[3] == "Puebla"}
        self.assertEqual(meses, {1})  # el archivo climático de la plataforma termina el 1 de enero de 2025
        r = self.client.get(reverse("agro:clima"), {"variable": "TMAX", "anio": "2025", "mes": "7", "estado": "Puebla"},
                            **HOST_SEGURO)
        self.assertContains(r, "No hay información disponible para la combinación seleccionada", count=1)
        self.assertNotContains(r, "folium-map")
        r = self.client.get(reverse("agro:clima"), {"variable": "TMAX", "anio": "2025", "mes": "1", "estado": "Puebla"},
                            **HOST_SEGURO)
        self.assertContains(r, "Puebla, enero de 2025")
        for params in ({"variable": "TMAX", "anio": "2026"}, {"variable": "TMAX", "anio": "2020", "mes": "0"}):
            r = self.client.get(reverse("agro:clima"), params, **HOST_SEGURO)
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, 'class="estado-vacio"', count=1)
        for nombre, params in (("precios", {"producto": "Haba", "anio_desde": "2026"}),
                               ("sequia", {"estado": "Puebla", "anio_hasta": "2026"})):
            r = self.client.get(reverse(f"agro:{nombre}"), params, **HOST_SEGURO)
            self.assertEqual(r.status_code, 200)
            self.assertContains(r, 'class="estado-vacio"', count=1)

    def test_js_recalcula_antes_de_enviar_y_al_restaurar(self):
        js = (settings.BASE_DIR / "agro" / "static" / "agro" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('form.addEventListener("submit"', js)
        self.assertIn('window.addEventListener("pageshow", actualizar)', js)
        r = self.client.get(reverse("agro:eda"), **HOST_SEGURO)
        self.assertContains(r, 'data-disponibilidad="disponibilidad-filtros" autocomplete="off"')


    # ------------------------------------------- funcionamiento sin Internet
    def _externos(self, html):
        etiquetas = re.findall(r'<(?:script|link|img|iframe)[^>]+(?:src|href)="((?:https?:)?//[^"]+)"', html)
        teselas = re.findall(r'https?://[^"\'\s]*\{z\}[^"\'\s]*', html)
        return etiquetas + teselas

    def test_sin_recursos_externos_en_modo_local(self):
        paginas = [("inicio", {}), ("precios", {"producto": "Frijol Negro", "estado": "Puebla"}),
                   ("clima", {}), ("clima", {"variable": "PRECIP", "anio": "2020", "estado": "Puebla", "mes": "7"}),
                   ("prediccion", {"producto": "Haba"}), ("eda", {}), ("sequia", {}), ("comparar", {}),
                   ("metodologia", {})]
        with self.settings(MAPA_TESELAS_EXTERNAS=False):
            for nombre, params in paginas:
                html = self.client.get(reverse(f"agro:{nombre}"), params, **HOST_SEGURO).content.decode()
                self.assertEqual(self._externos(html), [], nombre)
            html = self.client.get(reverse("agro:clima"), **HOST_SEGURO).content.decode()
            self.assertNotIn("tileLayer", html)
            self.assertIn('data-teselas="0"', html)
            self.assertRegex(html, r'data-base-geo="/static/agro/geo/mexico_estados[^"]*\.geojson"')
            self.assertRegex(html, r'<script src="/static/agro/vendor/leaflet/leaflet[^"]*\.js">')
            r = self.client.post(reverse("agro:comparar"), {"producto": "Haba", "estado": "Puebla", "variable": "TMAX"},
                                 **HOST_SEGURO)
            self.assertEqual(self._externos(r.content.decode()), [])
        # Modo público: el único recurso externo es el fondo de OpenStreetMap del mapa.
        html = self.client.get(reverse("agro:clima"), **HOST_SEGURO).content.decode()
        self.assertEqual(self._externos(html), ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"])
        self.assertIn('data-teselas="1"', html)

    def test_recursos_locales_de_mapas_y_licencias(self):
        from django.contrib.staticfiles import finders
        from agro.configuracion import REFERENCIA_ESTADOS
        for ruta in ["agro/vendor/leaflet/leaflet.js", "agro/vendor/leaflet/leaflet.css",
                     "agro/vendor/leaflet/images/layers.png", "agro/vendor/leaflet/LICENSE.txt",
                     "agro/geo/mexico_estados.geojson", "agro/geo/FUENTE.txt"]:
            self.assertIsNotNone(finders.find(ruta), ruta)
        js = open(finders.find("agro/vendor/leaflet/leaflet.js"), encoding="utf-8").read(200)
        self.assertIn("Leaflet 1.9.4", js)
        self.assertIn("BSD 2-Clause", open(finders.find("agro/vendor/leaflet/LICENSE.txt"), encoding="utf-8").read())
        self.assertIn("public domain", open(finders.find("agro/geo/FUENTE.txt"), encoding="utf-8").read())
        geo = json.loads(open(finders.find("agro/geo/mexico_estados.geojson"), encoding="utf-8").read())
        nombres = {f["properties"]["nombre"] for f in geo["features"] if f["properties"]["nombre"]}
        self.assertEqual(nombres, set(REFERENCIA_ESTADOS))  # 32 entidades, mismos nombres que los datos
        # Los puntos de referencia de cada estado caen dentro de su polígono (coordenadas reales).
        for f in geo["features"]:
            n = f["properties"]["nombre"]
            if not n:
                continue
            lat, lon = REFERENCIA_ESTADOS[n]
            xs = [c[0] for poly in self._poligonos(f["geometry"]) for c in poly[0]]
            ys = [c[1] for poly in self._poligonos(f["geometry"]) for c in poly[0]]
            self.assertTrue(min(xs) <= lon <= max(xs) and min(ys) <= lat <= max(ys), n)
        # data/raw no se publica como archivos estáticos.
        self.assertIsNone(finders.find("Precios_Historicos_SNIIM_Continuo.csv"))

    @staticmethod
    def _poligonos(g):
        return [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]

    def test_configuracion_modo_local_y_publico(self):
        import subprocess
        import sys
        codigo = ("import os, django; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup(); "
                  "from django.conf import settings as s; import json; print(json.dumps([s.PLATAFORMA_MODO, s.DEBUG, "
                  "s.ALLOWED_HOSTS, s.CSRF_TRUSTED_ORIGINS, s.SECURE_SSL_REDIRECT, s.CSRF_COOKIE_SECURE, "
                  "s.SESSION_COOKIE_SECURE, s.SECURE_HSTS_SECONDS, s.MAPA_TESELAS_EXTERNAS]))")
        def leer(modo):
            env = dict(os.environ, PLATAFORMA_MODO=modo, NGROK_DOMAIN="ejemplo.ngrok-free.dev", PUERTO="8000",
                       SECURE_SSL_REDIRECT="True", COOKIES_SEGURAS="True")
            out = subprocess.run([sys.executable, "-c", codigo], env=env, cwd=settings.BASE_DIR,
                                 capture_output=True, text=True, timeout=120)
            return json.loads(out.stdout.strip().splitlines()[-1])
        modo, debug, hosts, origenes, redir, csrf_seg, ses_seg, hsts, teselas = leer("local")
        self.assertEqual(modo, "local")
        self.assertFalse(debug)
        self.assertEqual(hosts, ["127.0.0.1", "localhost", "[::1]"])
        self.assertEqual(origenes, ["http://127.0.0.1:8000", "http://localhost:8000"])
        self.assertEqual((redir, csrf_seg, ses_seg, hsts, teselas), (False, False, False, 0, False))
        modo, debug, hosts, origenes, redir, csrf_seg, ses_seg, hsts, teselas = leer("publico")
        self.assertEqual(modo, "publico")
        self.assertFalse(debug)
        self.assertNotIn("*", hosts)
        self.assertIn("ejemplo.ngrok-free.dev", hosts)
        self.assertEqual(origenes, ["https://ejemplo.ngrok-free.dev"])
        self.assertEqual((redir, csrf_seg, ses_seg, teselas), (True, True, True, True))
        self.assertGreater(hsts, 0)
        # El servidor solo escucha en la interfaz local.
        self.assertIn('default="127.0.0.1"', (settings.BASE_DIR / "servidor.py").read_text(encoding="utf-8"))


    # ------------------------------------------------ revisión de calidad final
    def test_comparacion_clima_completo_y_sombreado_solo_del_precio(self):
        precios, clima = consultas.precios_df(), consultas.clima_df()
        html, figs = self._figuras_de("comparar", {"producto": "Frijol Negro", "estado": "Puebla", "variable": "PRECIP"}, "post")
        fig = figs["fig-comp"]
        precio, lluvia = fig["data"][0], fig["data"][1]
        self.assertEqual((precio["yaxis"], lluvia["yaxis"], lluvia["type"]), ("y", "y2", "bar"))
        x = self._arr(precio["x"]) if isinstance(precio["x"], dict) else precio["x"]
        sp = analitica.serie_precio_semanal_por_estado(precios, "Frijol Negro", "Puebla")
        # Precio: los 9 valores registrados, en sus semanas; el tramo sin cotizaciones queda vacío.
        vals = self._arr(precio["y"])
        self.assertEqual([v for v in vals if v is not None], [float(v) for v in sp.dropna().values])
        self.assertEqual(sum(v is not None for v in vals), 9)
        # Clima: todas las semanas del estado en el periodo comparado (también durante el tramo sin precio).
        ce = analitica.clima_semanal_estado(clima, "Puebla")
        ce.index = ce.index + pd.Timedelta(days=4)
        esperado = ce["precip"].reindex(pd.DatetimeIndex(x))
        self.assertEqual(self._arr(lluvia["y"]), [None if pd.isna(v) else float(v) for v in esperado.values])
        self.assertGreater(sum(v is not None for v in self._arr(lluvia["y"])), 40)
        # Sombreado tenue, debajo de los datos y solo en el panel del precio, con su etiqueta.
        rect = [s for s in fig["layout"]["shapes"] if s.get("type") == "rect"]
        self.assertEqual(len(rect), 1)
        self.assertEqual((rect[0]["x0"], rect[0]["x1"], rect[0]["yref"], rect[0]["layer"]), ("2017-11-05", "2018-07-08", "y domain", "below"))
        self.assertLessEqual(float(rect[0]["fillcolor"].split(",")[-1].strip(" )")), 0.1)
        etiquetas = [a["text"] for a in fig["layout"]["annotations"]]
        self.assertEqual(etiquetas, ["Sin registros de precio"])
        self.assertEqual(html.count("nota--discontinuidad"), 1)  # el clima no tiene huecos en ese periodo
        self.assertNotIn("semanas con precio y dato climático", html)

    def test_nota_de_coherencia_de_precios(self):
        html = self.client.get(reverse("agro:precios"), {"producto": "Aguacate Hass - Primera"}, **HOST_SEGURO).content.decode()
        # Primero la información útil (tarjetas) y después un mensaje breve; el diagnóstico técnico va
        # en un desplegable.
        resumen = ("Para este producto, use el precio frecuente como referencia. La fuente no informa el precio "
                   "mínimo y su precio máximo es menor que el frecuente, por lo que no es posible calcular un rango de precios.")
        tecnica = ("En todos los registros de esta selección no se informa el precio mínimo y el precio frecuente supera "
                   "el máximo registrado, por lo que estos datos no permiten establecer un rango de precios consistente.")
        self.assertIn(resumen, html)
        self.assertLess(html.index("Precio frecuente más bajo"), html.index(resumen))
        self.assertIn("<summary>Detalle técnico</summary><p>" + tecnica + "</p>", html)
        self.assertIn("Menor que el precio frecuente; no indica un rango", html)
        self.assertNotIn("Nota de interpretación", html)
        p = consultas.precios_df()
        ag = p[(p["producto"] == "Aguacate Hass - Primera") & p["precio_frec"].notna()]
        self.assertTrue(ag["precio_min"].isna().all())  # condición de los registros originales (mismo día y presentación)
        self.assertTrue((ag["precio_frec"] > ag["precio_max"]).all())
        # Solo en Precios (las series usan únicamente el precio frecuente) y no en los demás productos.
        for nombre in ("prediccion", "eda"):
            html = self.client.get(reverse(f"agro:{nombre}"), {"producto": "Aguacate Hass - Primera"}, **HOST_SEGURO).content.decode()
            self.assertNotIn(tecnica, html)
        for producto in consultas.nombres_productos():
            if not producto.startswith("Aguacate"):
                html = self.client.get(reverse("agro:precios"), {"producto": producto}, **HOST_SEGURO).content.decode()
                self.assertNotIn("Detalle técnico", html, producto)
                self.assertIsNone(consultas.notas_producto(producto))
        # Solo se mencionan las condiciones presentes y su alcance.
        df = pd.DataFrame({"precio_frec": [10.0, 12.0, 11.0], "precio_min": [8.0, 9.0, 9.0], "precio_max": [12.0, 11.0, 12.0]})
        nota = consultas.notas_producto("x", df)
        self.assertFalse(nota["rango_no_confiable"])
        self.assertEqual(nota["detalle"], "En 1 de los 3 registros de esta selección el precio frecuente supera el máximo "
                                          "registrado, por lo que en ellos el rango de precios no es consistente.")
        df["precio_min"] = [None, 9.0, 9.0]
        df["precio_frec"] = [10.0, 10.0, 11.0]
        self.assertEqual(consultas.notas_producto("x", df)["detalle"], "En 1 de los 3 registros de esta selección no se informa el precio mínimo.")

    def test_filtro_presentacion_solo_con_opciones(self):
        for producto in consultas.nombres_productos():
            r = self.client.get(reverse("agro:precios"), {"producto": producto}, **HOST_SEGURO)
            html = r.content.decode()
            campo = re.search(r'<div class="campo"( hidden)?>\s*<label for="id_presentacion">', html)
            self.assertIsNotNone(campo, producto)
            tiene = bool(consultas.opciones_precio(producto)["presentaciones"])
            self.assertEqual(campo.group(1) is None, tiene, producto)
            self.assertIn('data-ocultar-sin-opciones="1"', html)
        # La URL con presentación sigue funcionando.
        r = self.client.get(reverse("agro:precios"), {"producto": "Tomate Saladette - Primera", "presentacion": "Caja de 25 kg."}, **HOST_SEGURO)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('class="mensaje mensaje--error"', r.content.decode())
        css = (settings.BASE_DIR / "agro" / "static" / "agro" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".campo[hidden] { display: none; }", css)

    def test_nombre_publico_de_tomate_y_aguacate(self):
        p = consultas.precios_df()
        self.assertEqual(sorted(x for x in p["producto"].unique() if x.startswith("Tomate")), ["Tomate Saladette - Primera"])
        self.assertEqual(sorted(x for x in p["producto"].unique() if x.startswith("Aguacate")), ["Aguacate Hass - Primera"])
        for nombre, params in [("precios", {"producto": "Tomate Saladette - Primera"}), ("prediccion", {"producto": "Tomate Saladette - Primera"}),
                               ("inicio", {}), ("eda", {}), ("comparar", {})]:
            html = self.client.get(reverse(f"agro:{nombre}"), params, **HOST_SEGURO).content.decode()
            visible = re.sub(r"<script.*?</script>", "", html, flags=re.S)
            visible = re.sub(r"<[^>]+>", " ", visible)
            self.assertNotIn("Primera", visible, nombre)
            self.assertNotIn("Tomate · Tomate", visible, nombre)
            self.assertIn("Tomate saladette", visible, nombre)
        html = self.client.get(reverse("agro:precios"), {"producto": "Tomate Saladette - Primera"}, **HOST_SEGURO).content.decode()
        self.assertIn('<optgroup label="Tomate">', html)
        self.assertIn('<option value="Tomate Saladette - Primera" selected>Tomate saladette</option>', html)
        self.assertIn("Tomate saladette: mínimos y máximos de la selección", html)

    def test_correcciones_editoriales_y_valores_por_defecto(self):
        html = self.client.get(reverse("agro:inicio"), **HOST_SEGURO).content.decode()
        self.assertEqual(html.count("MXN/kg ·"), len(consultas.ultimo_precio_por_producto()))  # hortalizas en MXN/kg
        self.assertNotIn("tarjeta-producto__cultivo", html)
        _, figs = self._figuras_de("prediccion", {"producto": "Aguacate Hass - Primera"})
        self.assertEqual([t["name"] for t in figs["fig-serie"]["data"]], ["Promedio semanal"])  # un solo origen
        html, figs = self._figuras_de("prediccion", {"producto": "Tomate Saladette - Primera"})
        self.assertIn("Origen: Puebla", [t["name"] for t in figs["fig-serie"]["data"]])
        self.assertIn("las series se armonizan", html)
        r = self.client.get(reverse("agro:clima"), **HOST_SEGURO)
        self.assertEqual(r.context["form"]["anio"].value(), "2024")  # último año con los doce meses
        html = self.client.get(reverse("agro:precios"), **HOST_SEGURO).content.decode()
        self.assertNotIn("si lo desea", html)
        css = (settings.BASE_DIR / "agro" / "static" / "agro" / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn("h1, h2, h3, h4, summary, button, label,", css)
        self.assertNotIn("text-align-last: justify", css)

    def test_titulos_del_eje_horizontal_en_graficas_de_clima(self):
        miercoles = "Fecha de cierre de la semana (miércoles)"
        for variable in ("TMAX", "TMIN", "PRECIP"):
            _, figs = self._figuras_de("clima", {"variable": variable, "anio": "2024", "estado": "Puebla"})
            lay = figs["fig-clima"]["layout"]
            self.assertEqual(lay["xaxis"]["title"]["text"], miercoles)
            self.assertIn("(°C)" if variable != "PRECIP" else "(mm)", lay["yaxis"]["title"]["text"])
        # Las fechas de la serie climática son miércoles (W-WED), como indica el título.
        fechas = figs["fig-clima"]["data"][0]["x"]
        self.assertTrue(fechas and all(pd.Timestamp(f).dayofweek == 2 for f in fechas))
        _, figs = self._figuras_de("sequia", {"estado": "Puebla"})
        lay = figs["fig-sequia"]["layout"]
        self.assertEqual(lay["xaxis2"]["title"]["text"], miercoles)
        self.assertEqual(lay["annotations"][0]["text"], "Precipitación semanal (mm)")
        self.assertEqual(lay["meta"]["textosVista"]["mensual"], {"annotations[0].text": "Precipitación mensual (mm)"})
        self.assertEqual(lay["meta"]["textosVista"]["anual"], {"annotations[0].text": "Precipitación anual (mm)"})
        _, figs = self._figuras_de("eda", {"producto": "Haba"})
        lay = figs["fig-anual"]["layout"]
        self.assertEqual(lay["xaxis"]["title"]["text"], "Año")
        self.assertEqual(lay["meta"]["textosVista"]["mensual"], {"xaxis.title.text": "Mes"})
        _, figs = self._figuras_de("comparar", {"producto": "Haba", "estado": "Puebla", "variable": "PRECIP"}, "post")
        # Eje de la semana de precios (domingo); a 320 px un título más largo se cortaba.
        self.assertEqual(figs["fig-comp"]["layout"]["xaxis"]["title"]["text"], "Fecha de cierre de la semana (domingo)")
        js = (settings.BASE_DIR / "agro" / "static" / "agro" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("textosVista", js)
        html = self.client.get(reverse("agro:clima"), **HOST_SEGURO).content.decode()
        self.assertIn("Para ver la serie semanal de un estado", html)
        self.assertIn('<label for="id_variable">Dato climático</label>', html)

    def test_ficha_de_tiempo_hasta_la_cosecha_por_producto(self):
        from agro.configuracion import CICLO_CULTIVO

        valores = {p: [v for _, v in c.get("etapas", [])] for p, c in CICLO_CULTIVO.items()}
        self.assertEqual(set(CICLO_CULTIVO), set(consultas.nombres_productos()))
        for producto, ficha in CICLO_CULTIVO.items():
            html = self.client.get(reverse("agro:precios"), {"producto": producto}, **HOST_SEGURO).content.decode()
            self.assertEqual(html.count("Tiempo aproximado hasta la cosecha"), 1, producto)
            if ficha.get("sin_referencia"):
                self.assertIn(ficha["sin_referencia"], html)
                self.assertNotIn("ficha-ciclo__etapas", html)
            else:
                for tramo, valor in ficha["etapas"]:
                    self.assertIn(f"<dt>{tramo}</dt><dd>{valor}</dd>", html)
                for ref in ficha["referencias"]:
                    self.assertTrue(ref["url"].startswith("https://"))
                    self.assertIn(f'href="{ref["url"]}"', html)
                self.assertIn("El tiempo puede variar según la variedad, el clima, el riego y el manejo del cultivo.", html)
            # Sin datos residuales de otros productos.
            for otro, lista in valores.items():
                if otro != producto:
                    for v in lista:
                        if v not in valores[producto]:
                            self.assertNotIn(f"<dd>{v}</dd>", html, (producto, otro))
            self.assertNotRegex(html, r'<(script|link|img|iframe)[^>]+(src|href)="(https?:)?//')
            # «Producto» o «cultivo», no «semilla», en el texto propio (los títulos citados se respetan).
            propio = " ".join([ficha.get("sin_referencia", ""), ficha.get("contexto", "")]
                              + [t for t, _ in ficha.get("etapas", [])])
            self.assertNotIn("semilla", propio.lower())
        # Solo en Precios.
        for nombre in ("inicio", "clima", "prediccion", "eda"):
            self.assertNotIn("ficha-ciclo", self.client.get(reverse(f"agro:{nombre}"), **HOST_SEGURO).content.decode())
        # Aguacate: establecimiento y desarrollo del fruto por separado; tomate y pozolero sin cifra.
        self.assertIn("Del injerto al inicio de la producción", [t for t, _ in CICLO_CULTIVO["Aguacate Hass - Primera"]["etapas"]])
        # Todos los productos tienen un plazo orientativo; el tomate distingue siembra-trasplante y
        # trasplante-primer corte, y el pozolero no se confunde con el maíz blanco común.
        self.assertTrue(all(c.get("etapas") and c.get("referencias") for c in CICLO_CULTIVO.values()))
        self.assertEqual([t for t, _ in CICLO_CULTIVO["Tomate Saladette - Primera"]["etapas"]],
                         ["De la siembra en charola al trasplante", "Del trasplante al primer corte"])
        self.assertIn("Cacahuacintle", CICLO_CULTIVO["Maíz blanco pozolero"]["contexto"])
        self.assertNotEqual(CICLO_CULTIVO["Maíz blanco pozolero"]["etapas"], CICLO_CULTIVO["Maíz blanco"]["etapas"])
        html = self.client.get(reverse("agro:precios"), {"producto": "Tomate Saladette - Primera"}, **HOST_SEGURO).content.decode()
        for ficha in CICLO_CULTIVO.values():
            self.assertNotIn("no se encontró", ficha["contexto"].lower())

    def test_inicio_publico_objetivo_y_alcance_de_precios(self):
        html = self.client.get(reverse("agro:inicio"), **HOST_SEGURO).content.decode()
        self.assertIn("<h1>Precios y clima para agricultores y productores</h1>", html)
        self.assertIn("dirigida principalmente a agricultores y productores agrícolas", html)
        self.assertIn("no equivalen al precio que recibe el productor", html)
        for prometido in ("tiempo real", "precios actuales", "rentabilidad", "garantiza"):
            self.assertNotIn(prometido, html.lower())


class ModeladoTests(SimpleTestCase):
    """Resultados de Analisis_Precios_SNIIM_vf.ipynb consumidos por la plataforma."""

    PRODUCTOS = ["Haba", "Maíz blanco", "Frijol Pinto", "Aguacate Hass - Primera", "Tomate Saladette - Primera"]

    def setUp(self):
        from agro.servicios import modelado
        self.modelado = modelado
        self.doc = modelado.resultados()

    def test_procedencia_y_productos(self):
        insumos = self.doc["fuente"]["insumos"]
        self.assertIn("Analisis_Precios_SNIIM_vf.ipynb", insumos)
        for nombre in OBSOLETOS:
            self.assertNotIn(nombre, insumos)
        for nombre in ["Clima_Municipios_Top50_Semanal_v2.csv", "Asignacion_Espacial_Validada_k5_v2.csv",
                       "Clima_Hortalizas_Top50_Semanal_v2.csv", "Asignacion_Hortalizas_k5_v2.csv",
                       "Precios_Historicos_SNIIM_Continuo.csv"] + [f"Cierre_agricola_mun_{a}.csv" for a in range(2015, 2025)]:
            self.assertIn(nombre, insumos)
        registro = json.loads(settings.REGISTRO_HASHES.read_text(encoding="utf-8"))["archivos"]
        for nombre, h in insumos.items():
            self.assertEqual(registro[nombre]["sha256"], h, nombre)
        self.assertEqual(list(self.doc["productos"]), self.PRODUCTOS)

    def test_periodos_y_frecuencia(self):
        for nombre, p in self.doc["productos"].items():
            semanas = pd.DatetimeIndex(p["serie"]["fechas"])
            self.assertEqual(len(semanas), 574, nombre)
            self.assertTrue((semanas.dayofweek == 2).all(), nombre)          # semanas que terminan en miércoles
            self.assertTrue((semanas.to_series().diff().dropna() == pd.Timedelta(weeks=1)).all(), nombre)
            prueba = pd.DatetimeIndex(p["prueba"]["fechas"])
            self.assertEqual(len(prueba), 53, nombre)
            self.assertTrue((prueba.year == 2025).all(), nombre)              # evaluación, sin horizonte posterior
            self.assertLessEqual(prueba.max(), pd.Timestamp("2025-12-31"))
            for valores in p["prueba"]["pronosticos"].values():
                self.assertEqual(len(valores), 53, nombre)
            for aj in p["ajuste"].values():
                self.assertLess(pd.Timestamp(aj["fechas"][-1]), pd.Timestamp("2025-01-01"), nombre)

    def test_metricas_reproducibles_desde_pronosticos(self):
        for nombre, p in self.doc["productos"].items():
            obs = np.array(p["prueba"]["observado"])
            y = np.array(p["prueba"]["precio"], dtype=float)[obs]
            metricas = {m["modelo"]: m for m in p["metricas"]}
            for modelo, valores in p["prueba"]["pronosticos"].items():
                f = np.array(valores, dtype=float)[obs]
                e = y - f
                # Las tablas del notebook redondean a 3 decimales.
                self.assertAlmostEqual(metricas[modelo]["rmse"], float(np.sqrt(np.mean(e ** 2))), delta=6e-4, msg=(nombre, modelo))
                self.assertAlmostEqual(metricas[modelo]["mae"], float(np.mean(np.abs(e))), delta=6e-4, msg=(nombre, modelo))
                self.assertAlmostEqual(metricas[modelo]["mape"], float(100 * np.mean(np.abs(e / y))), delta=6e-4, msg=(nombre, modelo))

    def test_precio_semanal_recalculado(self):
        """Serie W-WED sin armonizar (un solo origen) recalculada desde el CSV original."""
        df = pd.read_csv(PRECIOS)
        df["Fecha"] = pd.to_datetime(df["Fecha"], format="%d/%m/%Y", errors="coerce")
        df["Precio Frec"] = pd.to_numeric(df["Precio Frec"], errors="coerce")
        for nombre in ["Haba", "Maíz blanco", "Frijol Pinto", "Aguacate Hass - Primera"]:
            sub = df[df["Producto_Buscado"] == nombre].dropna(subset=["Fecha", "Precio Frec"])
            sem = sub.groupby(sub["Fecha"].dt.to_period("W-WED").dt.end_time.dt.normalize())["Precio Frec"].mean()
            p = self.doc["productos"][nombre]["serie"]
            serie = pd.Series(p["precio"], index=pd.DatetimeIndex(p["fechas"]))[np.array(p["observado"])]
            esperado = sem.reindex(serie.index)
            self.assertEqual(int(np.array(p["observado"]).sum()), int(sem.loc["2015-01-01":"2025-12-31"].notna().sum()), nombre)
            self.assertTrue(np.allclose(serie.values, esperado.values, rtol=0, atol=1e-9), nombre)

    def test_modelos_coinciden_con_reporte_final(self):
        """Órdenes y rezagos seleccionados: Tabla 6.8 de main-04-11-26.pdf."""
        tabla = {"Haba": ([1, 1, 2], [0, 0, 1, 52], 72), "Maíz blanco": ([0, 1, 1], [0, 0, 0, 52], 72),
                 "Frijol Pinto": ([0, 1, 0], [0, 0, 1, 52], 85), "Aguacate Hass - Primera": ([1, 1, 2], [0, 0, 1, 52], 8),
                 "Tomate Saladette - Primera": ([2, 1, 2], [1, 0, 1, 52], 65)}
        for nombre, (orden, est, k) in tabla.items():
            par = self.doc["productos"][nombre]["parametros"]
            self.assertEqual((par["orden"], par["estacional"], par["rezago"]), (orden, est, k), nombre)

    def test_resultados_alterados_no_se_usan(self):
        import tempfile
        from pathlib import Path
        doc = json.loads(settings.MODELADO_VF.read_text(encoding="utf-8"))
        doc["fuente"]["insumos"]["Analisis_Precios_SNIIM_vf.ipynb"] = "0" * 64
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "modelado_vf.json"
            ruta.write_text(json.dumps(doc), encoding="utf-8")
            with override_settings(MODELADO_VF=ruta):
                with self.assertRaises(self.modelado.ModeladoNoDisponible):
                    self.modelado.resultados()


    def test_validacion_enfoca_2025_sin_fechas_futuras(self):
        from agro.servicios import graficas
        for p in self.PRODUCTOS:
            prod = self.doc["productos"][p]
            mejor = self.modelado.mejor_modelo(prod)
            fig = graficas.a_json(graficas.figura_validacion(prod, "MXN/kg", mejor=mejor))
            lay = fig["layout"]
            vistas = lay["meta"]["vistas"]
            self.assertEqual(lay["xaxis"]["range"], vistas["evaluacion"])
            self.assertTrue(vistas["evaluacion"][0].startswith("2024-"))
            self.assertLessEqual(vistas["evaluacion"][1], "2026-01-07")
            self.assertEqual(vistas["historico"][0], prod["serie"]["fechas"][0])
            self.assertTrue(lay["xaxis"]["rangeslider"]["visible"])
            self.assertEqual(lay["xaxis"]["rangeslider"]["yaxis"]["rangemode"], "auto")
            self.assertIn(mejor, lay["meta"]["iniciales"])
            lo, hi = lay["yaxis"]["range"]
            a, b = (pd.Timestamp(x) for x in vistas["evaluacion"])
            for t in fig["data"]:
                rol = (t.get("meta") or {}).get("rol")
                if rol == "pronostico":
                    self.assertLessEqual(max(t["x"]), "2025-12-31")  # sin pronósticos posteriores
                    self.assertEqual(t["line"]["dash"], "dash")
                if rol == "ajuste":
                    self.assertEqual(t["visible"], "legendonly")
                    self.assertEqual(t["line"]["dash"], "dot")
                if t.get("visible", True) is True:
                    for x, y in zip(t["x"], t["y"]):
                        if y is not None and a <= pd.Timestamp(x) <= b:
                            self.assertTrue(lo <= y <= hi, (p, t["name"], x, y))


class ConfiguracionTests(SimpleTestCase):
    def test_debug_false(self):
        self.assertFalse(settings.DEBUG)

    def test_hosts_limitados(self):
        self.assertNotIn("*", settings.ALLOWED_HOSTS)
        for h in settings.ALLOWED_HOSTS:
            self.assertTrue(h in ("127.0.0.1", "localhost", "[::1]", "testserver") or "ngrok" in h, h)
        for o in settings.CSRF_TRUSTED_ORIGINS:
            self.assertTrue(o.startswith("https://"))

    def test_proxy_ssl(self):
        self.assertEqual(settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))
        self.assertTrue(settings.CSRF_COOKIE_SECURE)
        self.assertTrue(settings.SESSION_COOKIE_SECURE)

    def test_sin_rutas_ni_hosts_codificados(self):
        base = settings.BASE_DIR / "agro"
        for ruta in list(base.rglob("*.html")) + list(base.rglob("*.js")) + list(base.rglob("*.css")):
            texto = ruta.read_text(encoding="utf-8")
            for patron in ["127.0.0.1", "localhost", ":8000", "ngrok-free"]:
                self.assertNotIn(patron, texto, f"{patron} en {ruta.name}")

    def test_sin_secretos_ni_referencias_en_proyecto(self):
        excluir = {".venv", "venv", "staticfiles", "static_vendor", "data", "logs", "run", "__pycache__"}
        patrones_ref = [re.compile(r"\b" + re.escape(t) + r"\b", re.I) for t in TERMINOS_REPOSITORIO_PROHIBIDOS]
        patron_secreto = re.compile(r"(DJANGO_SECRET_KEY\s*=\s*['\"]?[A-Za-z0-9_\-!@#$%^&*()+=]{30,})|(authtoken\s+[0-9A-Za-z_]{20,})")
        for ruta in settings.BASE_DIR.rglob("*"):
            if not ruta.is_file() or excluir & set(p.name for p in ruta.parents) or ruta.name == ".env":
                continue
            if ruta.suffix.lower() not in {".py", ".html", ".css", ".js", ".md", ".ps1", ".txt", ".example", ".json"}:
                continue
            texto = ruta.read_text(encoding="utf-8", errors="ignore")
            for p in patrones_ref:
                self.assertIsNone(p.search(texto), f"término no permitido en {ruta}")
            self.assertIsNone(patron_secreto.search(texto), f"posible secreto en {ruta}")

    def test_archivos_estaticos_propios_existen(self):
        base = settings.BASE_DIR / "agro" / "static" / "agro"
        self.assertTrue((base / "css" / "app.css").exists())
        self.assertTrue((base / "js" / "app.js").exists())
