"""Vistas de la plataforma."""
from __future__ import annotations

import logging

import pandas as pd

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods, require_safe

from . import forms
from .configuracion import (
    CICLO_CULTIVO,
    HUECO_MIN_SEMANAS,
    MESES,
    UMBRAL_FALTANTES_PCT,
    UMBRALES_TERMICOS,
    UNIDAD_PRECIO,
    VARIABLES_CLIMA,
    cumple_umbral,
    nombre_publico,
)
from .servicios import analitica, consultas, graficas
from .servicios import modelado
from .servicios.mapas import mapa_clima

log = logging.getLogger("agro")
SIN_DATOS = "No hay información disponible para la selección actual. Seleccione otro periodo o ubicación."
FILTROS_INVALIDOS = "Revise los filtros marcados e intente de nuevo."
SIN_COINCIDENCIA = "No hay información coincidente para la selección actual."


def _unidad(producto):
    return UNIDAD_PRECIO.get(consultas.categoria_de(producto) or "", "MXN")


def _invalido(ctx, form):
    """Un único mensaje: el error general del formulario (combinación sin datos) o el
    aviso de campos inválidos, que se marcan en el propio formulario."""
    generales = form.non_field_errors()
    ctx["sin_datos"] = generales[0] if generales else FILTROS_INVALIDOS
    ctx["errores_en_vacio"] = bool(generales)
    return ctx


def _huecos(fechas, regla="W-SUN", serie=None):
    """Intervalos de HUECO_MIN_SEMANAS semanas o más sin observaciones (nota y sombreado)."""
    lista = analitica.intervalos_sin_observaciones(fechas, regla, HUECO_MIN_SEMANAS)
    if serie:
        for h in lista:
            h["serie"] = serie
    return lista


def _cobertura_origenes(producto, resultado):
    """Origenes combinados sin ajuste de nivel en la serie semanal (granos con varios
    estados en la columna Origen): periodo cubierto por cada uno, tomado de los registros."""
    if resultado.get("por_origen"):
        return []
    p = consultas.precios_df()
    sub = p[(p["producto"] == producto)].dropna(subset=["fecha", "precio_frec"])
    g = sub.groupby(sub["estado_aux"].fillna("Sin origen"))["fecha"].agg(["min", "max", "count"])
    if len(g) < 2:
        return []
    return [{"origen": o, "desde": r["min"].date(), "hasta": r["max"].date(), "registros": int(r["count"])}
            for o, r in g.sort_values("min").iterrows()]


def _primero(lista, defecto=None):
    return lista[0] if lista else defecto


def _hay_datos():
    return bool(consultas.productos())


def _sin_carga(request, plantilla, extra=None):
    ctx = {"sin_carga": True}
    ctx.update(extra or {})
    return render(request, plantilla, ctx)


@require_safe
def inicio(request):
    if not _hay_datos():
        return _sin_carga(request, "agro/inicio.html")
    return render(request, "agro/inicio.html", {
        "resumen": consultas.resumen_general(),
        "ultimos": consultas.ultimo_precio_por_producto(),
        "unidades": UNIDAD_PRECIO,
    })


@require_safe
def precios(request):
    if not _hay_datos():
        return _sin_carga(request, "agro/precios.html")
    productos = consultas.productos()
    producto = request.GET.get("producto") or productos[0]["producto"]
    nombres = consultas.nombres_productos()
    opciones = consultas.opciones_precio(producto) if producto in nombres else None
    datos = request.GET if "producto" in request.GET else None
    disp = consultas.disponibilidad_precios()
    form = forms.FiltroPrecios(datos, productos=productos, opciones=opciones,
                               initial={"producto": producto}, disponibilidad=disp)
    ctx = {"form": form, "disponibilidad": disp, "tabla_cultivos": consultas_tabla_cultivos(request)}
    if datos is not None and not form.is_valid():
        return render(request, "agro/precios.html", _invalido(ctx, form))
    f = form.cleaned_data if datos is not None else {"producto": producto}
    producto = f["producto"]
    sub = analitica.filtrar_precios(
        consultas.precios_df(), producto, f.get("estado") or None, f.get("presentacion") or None,
        f.get("anio_desde") or None, f.get("anio_hasta") or None,
    )
    sub = sub[sub["precio_frec"].notna() | sub["precio_max"].notna()]
    unidad = _unidad(producto)
    ctx.update({"producto": producto, "unidad": unidad,
                "nota_rango": consultas.notas_producto(producto, sub),
                "ciclo": CICLO_CULTIVO.get(producto)})
    if sub.empty:
        ctx["sin_datos"] = SIN_DATOS
    else:
        grupos = list(sub.groupby([sub["estado_aux"].fillna("Sin origen"), sub["presentacion"].fillna("")], sort=True))
        huecos = []
        for (estado, pres), g in grupos:
            nombre = (estado if not pres else f"{estado} · {pres}") if len(grupos) > 1 else None
            huecos += _huecos(g.loc[g["precio_frec"].notna(), "fecha"], serie=nombre)
        ctx.update({
            "huecos": huecos,
            "huecos_sombreados": len(grupos) == 1,
            "grafica": graficas.a_json(graficas.figura_precios(sub, unidad, revision=producto,
                                                               huecos=huecos if len(grupos) == 1 else None)),
            "resumen": analitica.resumen_min_max(sub),
            "tabla_anual": analitica.tabla_anual(sub),
        })
    return render(request, "agro/precios.html", ctx)


def consultas_tabla_cultivos(request):
    anio = request.GET.get("anio_tabla")
    anios = consultas.anios_precios()
    if anio and (not anio.isdigit() or int(anio) not in anios):
        anio = None
    filas = analitica.tabla_min_max_por_producto(consultas.precios_df(), anio)
    for fila in filas:
        fila["unidad"] = UNIDAD_PRECIO.get(fila["categoria"], "MXN")
    return {"filas": filas, "anio": anio, "anios": anios}


@require_safe
def clima(request):
    if not consultas.anios_clima():
        return _sin_carga(request, "agro/clima.html")
    # Opciones del formulario y del navegador desde el mismo catálogo de disponibilidad.
    disp = consultas.disponibilidad_clima()
    anios = consultas.valores_disponibles(disp, "anio")
    estados = consultas.valores_disponibles(disp, "estado")
    meses = consultas.valores_disponibles(disp, "mes")
    # Año inicial: el más reciente con los doce meses de temperatura máxima (el archivo
    # climático termina en la primera semana de 2025, que solo cubre enero).
    meses_por_anio = {}
    for f in disp["filas"]:
        if f[0] == "TMAX":
            meses_por_anio.setdefault(f[1], set()).add(f[2])
    completos = [a for a, m in meses_por_anio.items() if len(m) == 12]
    anio_defecto = max(completos) if completos else max(meses_por_anio)
    defecto = {"variable": "TMAX", "anio": str(anio_defecto), "mes": "", "estado": ""}
    datos = request.GET if "anio" in request.GET else defecto
    form = forms.FiltroClima(datos, anios=anios, estados=estados, meses=meses, disponibilidad=disp)
    ctx = {"form": form, "variables": VARIABLES_CLIMA, "disponibilidad": disp}
    if not form.is_valid():
        return render(request, "agro/clima.html", _invalido(ctx, form))
    f = form.cleaned_data
    variable, anio, mes = f["variable"], int(f["anio"]), (int(f["mes"]) if f.get("mes") else None)
    meta = VARIABLES_CLIMA[variable]
    periodo = f"{dict(MESES)[mes]} de {anio}" if mes else str(anio)
    df = consultas.clima_df()
    estado = f.get("estado") or ""
    # Todos los calculos del mapa usan solo la seleccion: estado, variable, año y mes.
    por_estacion = analitica.clima_mensual_por_estacion(df, variable.lower(), anio, mes, estado or None)
    por_estado = analitica.clima_por_estado(por_estacion)
    ctx.update({"meta": meta, "periodo": periodo, "variable": variable, "estado_mapa": estado})
    if por_estado.empty:
        ctx["sin_datos"] = SIN_DATOS
    else:
        ctx["mapa"] = mapa_clima(por_estado, por_estacion, variable, periodo, estado or None)
        ctx["tabla_estados"] = por_estado.to_dict("records")
        if estado:
            ctx["tabla_estaciones"] = por_estacion.sort_values("id_estacion").to_dict("records")
    if estado:
        ctx["estado"] = estado
        semanal = analitica.clima_semanal_estado(df, estado, anio, anio)
        if mes and not semanal.empty:
            semanal = semanal[semanal.index.month == mes]
        if semanal.empty or semanal[variable.lower()].notna().sum() == 0:
            ctx["serie_sin_datos"] = SIN_DATOS
        else:
            ctx["grafica_estado"] = graficas.a_json(graficas.figura_clima_estado(semanal, variable, revision=f"{estado}-{variable}"))
    return render(request, "agro/clima.html", ctx)


@require_safe
def prediccion(request):
    if not _hay_datos():
        return _sin_carga(request, "agro/prediccion.html")
    productos = consultas.productos()
    datos = request.GET if "producto" in request.GET else {"producto": productos[0]["producto"]}
    form = forms.FiltroProducto(datos, productos=productos)
    ctx = {"form": form, "umbral_faltantes": UMBRAL_FALTANTES_PCT}
    if not form.is_valid():
        return render(request, "agro/prediccion.html", _invalido(ctx, form))
    producto = form.cleaned_data["producto"]
    resultado = consultas.serie_analisis(producto)
    unidad = _unidad(producto)
    ctx.update({"producto": producto, "unidad": unidad})
    if not resultado or not resultado["serie"]:
        ctx["sin_datos"] = SIN_DATOS
        return render(request, "agro/prediccion.html", ctx)
    semanas = len(resultado["serie"])
    con_dato = sum(1 for p in resultado["serie"] if p["valor"] is not None)
    # Avisos generados al calcular la serie, redactados para la página.
    avisos = []
    for a in resultado["advertencias"]:
        if "historial insuficiente" in a:
            avisos.append(f"La serie tiene {con_dato} semanas con cotización; el análisis de tendencia y temporada "
                          "requiere al menos 104 (dos años), por lo que no se calcula.")
        else:
            avisos.append(a.replace(f"{producto}:", f"{nombre_publico(producto)}:", 1))
    huecos = _huecos(analitica.fechas_observadas(resultado["serie"]))
    ctx.update({
        "huecos": huecos,
        "avisos_serie": avisos,
        "cobertura_origenes": _cobertura_origenes(producto, resultado),
        "resultado": resultado,
        "semanas": semanas,
        "semanas_con_dato": con_dato,
        "desde": resultado["serie"][0]["fecha"],
        "hasta": resultado["serie"][-1]["fecha"],
        "grafica_serie": graficas.a_json(graficas.figura_serie_original(resultado, unidad, revision=producto,
                                                                        huecos=huecos)),
        "grafica_faltantes": graficas.a_json(graficas.figura_faltantes(resultado["mapa_faltantes"])),
        "grafica_stl": graficas.a_json(graficas.figura_stl(resultado, unidad, revision=producto)) if resultado["descomposicion"] else None,
    })
    ctx.update(_contexto_modelado(producto, unidad))
    return render(request, "agro/prediccion.html", ctx)


def _contexto_modelado(producto, unidad):
    """Validación 2025 del notebook final (resultados precalculados, sin entrenar aquí)."""
    try:
        doc = modelado.resultados()
    except modelado.ModeladoNoDisponible as e:
        log.error("Modelado no disponible: %s", e)
        return {"modelado_no_disponible": True}
    prod = doc["productos"].get(producto)
    if prod is None:
        nombres = [nombre_publico(p) for p in doc["productos"]]
        nombres = [n[:1].lower() + n[1:] for n in nombres]
        return {"productos_modelados": ", ".join(nombres[:-1]) + " y " + nombres[-1] if len(nombres) > 1 else "".join(nombres)}
    prueba = prod["prueba"]
    metricas = prod["metricas"]
    mejor = modelado.mejor_modelo(prod)
    por_nombre = {m["modelo"]: m for m in metricas}
    serie = prod["serie"]
    obs = [f for f, o in zip(serie["fechas"], serie["observado"]) if o]
    huecos = _huecos(obs, regla="W-WED")
    inicio = prueba["fechas"][0]
    return {
        "modelos_validacion": graficas.modelos_validacion(prod),
        "huecos_validacion": [h for h in huecos if h["hasta"] >= inicio],
        "modelo": prod,
        "modelo_metricas": metricas,
        "modelo_mejor": mejor,
        "modelo_rmse_mejor": por_nombre[mejor]["rmse"] if mejor else None,
        "modelo_rmse_sarimax": (por_nombre.get("SARIMAX") or {}).get("rmse"),
        "modelo_rmse_sarima": (por_nombre.get("SARIMA (sin clima)") or {}).get("rmse"),
        "prueba_desde": prueba["fechas"][0],
        "prueba_hasta": prueba["fechas"][-1],
        "prueba_semanas": len(prueba["fechas"]),
        "prueba_con_dato": sum(prueba["observado"]),
        "grafica_validacion": graficas.a_json(graficas.figura_validacion(prod, unidad, revision=f"val-{producto}",
                                                                         mejor=mejor, huecos=huecos)),
    }


@require_safe
def eda(request):
    if not _hay_datos():
        return _sin_carga(request, "agro/eda.html")
    productos = consultas.productos()
    datos = request.GET if "producto" in request.GET else {"producto": productos[0]["producto"]}
    disp = consultas.disponibilidad_eda()
    anios = consultas.valores_disponibles(disp, "anio_desde")
    form = forms.FiltroEDA(datos, productos=productos, anios=anios, disponibilidad=disp)
    ctx = {"form": form, "disponibilidad": disp}
    if not form.is_valid():
        return render(request, "agro/eda.html", _invalido(ctx, form))
    f = form.cleaned_data
    producto = f["producto"]
    unidad = _unidad(producto)
    serie = analitica.valores_por_mes(consultas.serie_eda(producto),
                                      f.get("anio_desde"), f.get("anio_hasta"))
    ctx.update({"producto": producto, "unidad": unidad})
    if serie.empty:
        ctx["sin_datos"] = SIN_DATOS
        return render(request, "agro/eda.html", ctx)
    matriz = analitica.matriz_anio_mes(serie)
    # Semana cuyo domingo de cierre es posterior al final del archivo de precios: se informa
    # una vez, con las fechas reales de sus cotizaciones, si forma parte de la selección.
    original = consultas.serie_semanal_original(producto).dropna()
    fin = consultas.precios_df()["fecha"].max()
    if len(original) and original.index.max() > fin and serie.index.max() == fin:
        cierre = original.index.max()
        p = consultas.precios_df()
        cot = p[(p["producto"] == producto) & (p["fecha"] > cierre - pd.Timedelta(days=7))
                & (p["fecha"] <= fin)].dropna(subset=["precio_frec"])
        if not cot.empty:
            ctx["semana_final"] = {"cierre": cierre.date(), "desde": cot["fecha"].min().date(),
                                   "hasta": cot["fecha"].max().date()}
    ctx.update({
        "semanas": int(len(serie)),
        "desde": serie.index.min().date(),
        "hasta": serie.index.max().date(),
        "promedio": float(serie.mean()),
        "minimo": float(serie.min()), "fecha_minimo": serie.idxmin().date(),
        "maximo": float(serie.max()), "fecha_maximo": serie.idxmax().date(),
        "grafica_caja": graficas.a_json(graficas.figura_caja_mensual(serie, unidad)),
        "grafica_matriz": graficas.a_json(graficas.figura_anio_mes(matriz, unidad)),
        "grafica_anual": graficas.a_json(graficas.figura_promedios(serie, unidad, revision=producto)),
        "vistas_promedio": [("anual", "Anual"), ("mensual", "Mensual")],
    })
    return render(request, "agro/eda.html", ctx)


@require_safe
def sequia(request):
    if not consultas.anios_clima():
        return _sin_carga(request, "agro/sequia.html")
    disp = consultas.disponibilidad_sequia()
    anios = consultas.valores_disponibles(disp, "anio_desde")
    estados = consultas.valores_disponibles(disp, "estado")
    datos = request.GET if "estado" in request.GET else {"estado": _primero(estados, "")}
    form = forms.FiltroSequia(datos, anios=anios, estados=estados, disponibilidad=disp)
    ctx = {"form": form, "umbrales": UMBRALES_TERMICOS, "disponibilidad": disp}
    if not form.is_valid():
        return render(request, "agro/sequia.html", _invalido(ctx, form))
    f = form.cleaned_data
    semanal = analitica.clima_semanal_estado(consultas.clima_df(), f["estado"],
                                             f.get("anio_desde"), f.get("anio_hasta"))
    ctx["estado"] = f["estado"]
    if semanal.empty:
        ctx["sin_datos"] = SIN_DATOS
        return render(request, "agro/sequia.html", ctx)
    ctx.update({
        "grafica": graficas.a_json(graficas.figura_sequia(semanal, UMBRALES_TERMICOS, revision=f["estado"])),
        "vistas_precip": [("semanal", "Semanal"), ("mensual", "Mensual"), ("anual", "Anual")],
        "conteos": analitica.conteo_umbrales(semanal, UMBRALES_TERMICOS, cumple_umbral),
        "semanas_temp_faltante": int(semanal["tmax"].isna().sum()),
    })
    return render(request, "agro/sequia.html", ctx)


@require_http_methods(["GET", "POST"])
def comparar(request):
    disp = consultas.disponibilidad_comparacion()
    # Solo combinaciones con al menos una semana comparada (cobertura común de precio y clima).
    comparables = {}
    for producto, estado, _ in disp["filas"]:
        comparables.setdefault(producto, [])
        if estado not in comparables[producto]:
            comparables[producto].append(estado)
    if not comparables:
        return _sin_carga(request, "agro/comparar.html")
    if request.method == "POST":
        form = forms.FormularioComparacion(request.POST, comparables=comparables, disponibilidad=disp)
    else:
        primero = sorted(comparables)[0]
        estado = comparables[primero][0]
        variables = [v for p, e, v in disp["filas"] if p == primero and e == estado]
        form = forms.FormularioComparacion(
            initial={"producto": primero, "estado": estado,
                     "variable": "PRECIP" if "PRECIP" in variables else variables[0]},
            comparables=comparables, disponibilidad=disp,
        )
    ctx = {"form": form, "comparables": comparables, "disponibilidad": disp}
    if request.method == "POST" and form.is_valid():
        f = form.cleaned_data
        precios = consultas.precios_df()
        serie_p = analitica.serie_precio_semanal_por_estado(precios, f["producto"], f["estado"])
        clima_e = analitica.clima_semanal_estado(consultas.clima_df(), f["estado"])
        unido, reporte = analitica.unir_precio_clima(serie_p, clima_e)
        meta = VARIABLES_CLIMA[f["variable"]]
        unidad = _unidad(f["producto"])
        ctx.update({"reporte": reporte, "seleccion": f, "meta": meta, "unidad": unidad,
                    "que_clima": f"datos de {meta['etiqueta'].lower()}"})
        if unido.empty:
            ctx["sin_datos"] = SIN_COINCIDENCIA
        else:
            ctx["resumen"] = analitica.resumen_comparacion(unido, f["variable"])
            ctx["presentaciones"] = analitica.presentaciones_comparadas(
                precios, f["producto"], f["estado"], unido["semana"])
            # Periodo comparado: de la primera a la última semana con precio y clima. Los
            # tramos sin dato se describen por fuente, sin confundir la falta de precio con
            # la falta de clima.
            ini, fin = unido["semana"].min(), unido["semana"].max()
            sp = serie_p[(serie_p.index >= ini) & (serie_p.index <= fin)].dropna()
            col = f["variable"].lower()
            cl = clima_e[col].dropna()
            cl_sem = analitica.semana_precio_de_fecha_clima(pd.Series(cl.index, index=cl.index))
            cl_sem = cl_sem[(cl_sem >= ini) & (cl_sem <= fin)]
            huecos = _huecos(sp.index)
            ctx["huecos"] = huecos
            ctx["huecos_clima"] = _huecos(cl_sem.values)
            ctx["grafica"] = graficas.a_json(graficas.figura_comparacion(
                unido, f["variable"], unidad, f["producto"], f["estado"], huecos=huecos,
                serie_precio=serie_p, clima_semanal=clima_e))
    return render(request, "agro/comparar.html", ctx)


@require_safe
def metodologia(request):
    from .models import CargaDatos

    cargas = {}
    for c in CargaDatos.objects.all()[:10][::-1]:
        cargas[c.tipo] = c
    return render(request, "agro/metodologia.html", {
        "cargas": cargas,
        "umbrales": UMBRALES_TERMICOS,
        "unidades": UNIDAD_PRECIO,
    })


@require_safe
def salud(request):
    return JsonResponse({"estado": "ok", "datos_cargados": _hay_datos()})


ICONO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="7" fill="#ffffff"/>'
    '<path d="M16 4c-5 6-7 10.5-7 14.5a7 7 0 0 0 14 0C23 14.5 21 10 16 4Z" fill="#1f8a5b"/>'
    '<path d="M16 12v16M16 20l-4-3M16 17l4-3" stroke="#0b4f35" stroke-width="2" '
    'stroke-linecap="round" fill="none"/></svg>'
)


@require_safe
def favicon(request):
    respuesta = HttpResponse(ICONO_SVG, content_type="image/svg+xml")
    respuesta["Cache-Control"] = "public, max-age=86400"
    return respuesta


def error_404(request, exception):
    return render(request, "agro/error.html", {"codigo": 404, "mensaje": "La página solicitada no existe."}, status=404)


def error_500(request):
    return render(request, "agro/error.html", {"codigo": 500, "mensaje": "Ocurrió un error inesperado. Intente nuevamente en unos minutos."}, status=500)
