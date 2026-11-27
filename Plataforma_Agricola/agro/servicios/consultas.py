"""Acceso a datos importados con cache en memoria por version de carga."""
from __future__ import annotations

import threading

import pandas as pd

from ..configuracion import CULTIVOS_ORDEN
from ..models import CargaDatos, ClimaRegistro, PrecioRegistro, SerieAnalisis
from .analitica import serie_original_df

_lock = threading.Lock()
_cache: dict = {}

CAMPOS_PRECIO = [
    "fila_origen", "fecha", "producto", "categoria", "cultivo_aux", "estado_aux",
    "origen", "origen_estado", "presentacion", "precio_min", "precio_max", "precio_frec",
]
CAMPOS_CLIMA = ["fecha", "precip", "tmax", "tmin", "id_estacion", "estado", "latitud", "longitud"]


def version_datos() -> str:
    ids = list(CargaDatos.objects.order_by("-id").values_list("id", flat=True)[:3])
    return "-".join(str(i) for i in ids) or "vacio"


def _memo(clave, fabrica):
    """Cache por version de carga.

    El calculo se ejecuta fuera del candado: varias fabricas llaman a su vez
    a _memo (por ejemplo productos() usa precios_df()); mantener el candado
    durante el calculo producia un bloqueo mutuo.
    """
    ver = version_datos()
    with _lock:
        if _cache.get("version") != ver:
            _cache.clear()
            _cache["version"] = ver
        if clave in _cache:
            return _cache[clave]
    valor = fabrica()
    with _lock:
        if _cache.get("version") == ver:
            return _cache.setdefault(clave, valor)
    return valor


def precios_df() -> pd.DataFrame:
    def fabrica():
        df = pd.DataFrame.from_records(PrecioRegistro.objects.values(*CAMPOS_PRECIO), columns=CAMPOS_PRECIO)
        df["fecha"] = pd.to_datetime(df["fecha"])
        for c in ["precio_min", "precio_max", "precio_frec"]:
            df[c] = pd.to_numeric(df[c])
        return df

    return _memo("precios", fabrica)


def clima_df() -> pd.DataFrame:
    def fabrica():
        df = pd.DataFrame.from_records(ClimaRegistro.objects.values(*CAMPOS_CLIMA), columns=CAMPOS_CLIMA)
        df["fecha"] = pd.to_datetime(df["fecha"])
        for c in ["precip", "tmax", "tmin", "latitud", "longitud"]:
            df[c] = pd.to_numeric(df[c])
        return df

    return _memo("clima", fabrica)


def productos() -> list[dict]:
    """Productos reales presentes, ordenados por cultivo."""
    def fabrica():
        df = precios_df()
        if df.empty:
            return []
        g = df.groupby(["producto", "cultivo_aux", "categoria"]).size().reset_index()
        orden = {c: i for i, c in enumerate(CULTIVOS_ORDEN)}
        g["o"] = g["cultivo_aux"].map(lambda c: orden.get(c, 99))
        g = g.sort_values(["o", "producto"])
        return [
            {"producto": r.producto, "cultivo": r.cultivo_aux, "categoria": r.categoria}
            for r in g.itertuples()
        ]

    return _memo("productos", fabrica)


def nombres_productos() -> list[str]:
    return [p["producto"] for p in productos()]


def categoria_de(producto) -> str | None:
    for p in productos():
        if p["producto"] == producto:
            return p["categoria"]
    return None


def opciones_precio(producto):
    """Opciones del formulario de Precios para un producto, tomadas del mismo catálogo
    de disponibilidad que usa el navegador (registros con precio frecuente o máximo)."""
    filas = [f for f in disponibilidad_precios()["filas"] if f[0] == producto]
    return {"estados": sorted({f[1] for f in filas if f[1]}),
            "presentaciones": sorted({f[2] for f in filas if f[2]}),
            "anios": sorted({f[3] for f in filas})}


def valores_disponibles(disp: dict, campo: str) -> list:
    """Valores de un campo presentes en el catálogo de disponibilidad (opciones del
    formulario construidas con la misma fuente que el navegador)."""
    col = disp["campos"][campo]
    return sorted({f[col] for f in disp["filas"] if f[col] != ""})


def anios_precios() -> list[int]:
    df = precios_df()
    return sorted(df["fecha"].dropna().dt.year.unique().astype(int).tolist())


def anios_clima() -> list[int]:
    df = clima_df()
    return sorted(df["fecha"].dt.year.unique().astype(int).tolist()) if not df.empty else []


def estados_clima() -> list[str]:
    df = clima_df()
    return sorted(df["estado"].unique().tolist()) if not df.empty else []


def serie_analisis(producto) -> dict | None:
    obj = SerieAnalisis.objects.filter(producto=producto).first()
    return obj.resultado if obj else None


def serie_semanal_original(producto) -> pd.Series:
    def fabrica():
        r = serie_analisis(producto)
        return serie_original_df(r["serie"]) if r else pd.Series(dtype=float)

    return _memo(("serie", producto), fabrica)


def serie_eda(producto) -> pd.Series:
    """Serie semanal para el análisis por año y mes (ver analitica.semanas_en_cobertura)."""
    def fabrica():
        from .analitica import semanas_en_cobertura

        return semanas_en_cobertura(serie_semanal_original(producto), precios_df()["fecha"].max())

    return _memo(("serie_eda", producto), fabrica)


def estados_comparables() -> dict[str, list[str]]:
    """Por producto, estados de origen que tambien existen en el archivo
    climatico (coincidencia exacta del nombre del estado)."""
    def fabrica():
        p = precios_df()
        clima = set(estados_clima())
        res = {}
        for prod, g in p.dropna(subset=["fecha", "precio_frec"]).groupby("producto"):
            est = sorted(set(g["estado_aux"].dropna()) & clima)
            if est:
                res[prod] = est
        return res

    return _memo("comparables", fabrica)


def resumen_general() -> dict:
    def fabrica():
        p = precios_df()
        c = clima_df()
        cargas = {k.tipo: k for k in CargaDatos.objects.all()[:10][::-1]}
        return {
            "productos": len(productos()),
            "cultivos": len({x["cultivo"] for x in productos()}),
            "registros_precio": int(p["precio_frec"].notna().sum()) if not p.empty else 0,
            "precio_desde": p["fecha"].min().date() if not p.empty else None,
            "precio_hasta": p["fecha"].max().date() if not p.empty else None,
            "registros_clima": int(len(c)),
            "estaciones": int(c["id_estacion"].nunique()) if not c.empty else 0,
            "estados_clima": int(c["estado"].nunique()) if not c.empty else 0,
            "clima_desde": c["fecha"].min().date() if not c.empty else None,
            "clima_hasta": c["fecha"].max().date() if not c.empty else None,
            "archivo_clima": cargas.get("clima").archivo if cargas.get("clima") else None,
        }

    return _memo("resumen", fabrica)


def ultimo_precio_por_producto() -> list[dict]:
    def fabrica():
        df = precios_df().dropna(subset=["fecha", "precio_frec"])
        filas = []
        for p in productos():
            sub = df[df["producto"] == p["producto"]].sort_values("fecha")
            if sub.empty:
                continue
            ultima = sub["fecha"].iat[-1]
            dia = sub[sub["fecha"] == ultima]
            filas.append({
                **p,
                "fecha": ultima.date(),
                "precio": float(dia["precio_frec"].mean()),
                "registros_dia": int(len(dia)),
            })
        return filas

    return _memo("ultimos", fabrica)


def _cifra(n: int) -> str:
    texto = str(n)
    return f"{texto[:-3]} {texto[-3:]}" if len(texto) > 4 else texto


def notas_producto(producto, registros=None):
    """Nota sobre la coherencia entre precio mínimo, máximo y frecuente, o None.

    Devuelve {"resumen", "detalle", "rango_no_confiable"}: el resumen dice al usuario qué
    dato usar; el detalle conserva el diagnóstico técnico (cuántos registros y qué
    condición). Se calcula con los mismos registros que muestra la vista (cada fila del
    CSV: misma fecha, presentación y origen), sin agregaciones.
    """
    if registros is None:
        df = precios_df()
        registros = df[(df["producto"] == producto) & df["fecha"].notna()]
    r = registros[registros["precio_frec"].notna()]
    n = int(len(r))
    if not n:
        return None
    sin_min = int(r["precio_min"].isna().sum())
    frec_mayor = int((r["precio_max"].notna() & (r["precio_frec"] > r["precio_max"])).sum())

    def alcance(k):
        return "En todos los registros" if k == n else f"En {_cifra(k)} de los {_cifra(n)} registros"

    if sin_min and frec_mayor:
        if sin_min == frec_mayor == n:
            return {
                "resumen": "Para este producto, use el precio frecuente como referencia. La fuente no informa "
                           "el precio mínimo y su precio máximo es menor que el frecuente, por lo que no es "
                           "posible calcular un rango de precios.",
                "detalle": "En todos los registros de esta selección no se informa el precio mínimo y el precio "
                           "frecuente supera el máximo registrado, por lo que estos datos no permiten establecer "
                           "un rango de precios consistente.",
                "rango_no_confiable": True,
            }
        detalle = (f"{alcance(sin_min)} de esta selección no se informa el precio mínimo, y en "
                   f"{_cifra(frec_mayor)} de {_cifra(n)} el precio frecuente supera el máximo registrado; "
                   "en esos registros el rango de precios no es consistente.")
    elif frec_mayor:
        detalle = (f"{alcance(frec_mayor)} de esta selección el precio frecuente supera el máximo registrado, "
                   "por lo que en ellos el rango de precios no es consistente.")
    elif sin_min:
        detalle = f"{alcance(sin_min)} de esta selección no se informa el precio mínimo."
    else:
        return None
    return {
        "resumen": "Use el precio frecuente como referencia principal: en parte de los registros el precio "
                   "mínimo o el máximo están incompletos o no son consistentes.",
        "detalle": detalle,
        "rango_no_confiable": False,
    }


# ------------------------------------------------- disponibilidad de filtros
# Combinaciones con datos reales, calculadas con los mismos criterios de cada vista.
# Alimentan los filtros dependientes (navegador) y la validación de los formularios.


def disponibilidad_precios() -> dict:
    """[producto, estado, presentación, año] con precio frecuente o máximo registrado."""
    def fabrica():
        df = precios_df()
        sub = df[df["fecha"].notna() & (df["precio_frec"].notna() | df["precio_max"].notna())]
        filas = (sub.assign(estado=sub["estado_aux"].fillna(""), pres=sub["presentacion"].fillna(""),
                            anio=sub["fecha"].dt.year.astype(int))
                 [["producto", "estado", "pres", "anio"]].drop_duplicates().sort_values(["producto", "estado", "pres", "anio"]))
        return {"campos": {"producto": 0, "estado": 1, "presentacion": 2, "anio_desde": 3, "anio_hasta": 3},
                "rangos": {"anio_desde": "desde", "anio_hasta": "hasta"},
                "filas": [[r.producto, r.estado, r.pres, int(r.anio)] for r in filas.itertuples()]}

    return _memo("disp_precios", fabrica)


def disponibilidad_eda() -> dict:
    """[producto, año] con al menos una semana con cotización en la serie del análisis
    por año y mes (la misma que agrega la vista)."""
    def fabrica():
        filas = []
        for p in nombres_productos():
            s = serie_eda(p).dropna()
            filas += [[p, int(a)] for a in sorted(set(s.index.year))]
        return {"campos": {"producto": 0, "anio_desde": 1, "anio_hasta": 1},
                "rangos": {"anio_desde": "desde", "anio_hasta": "hasta"}, "filas": filas}

    return _memo("disp_eda", fabrica)


def disponibilidad_clima() -> dict:
    """[variable, año, mes, estado] con al menos una semana con dato de la variable."""
    def fabrica():
        df = clima_df()
        filas = []
        for var in ("TMAX", "TMIN", "PRECIP"):
            sub = df[df[var.lower()].notna()]
            g = sub.assign(anio=sub["fecha"].dt.year, mes=sub["fecha"].dt.month)[["anio", "mes", "estado"]].drop_duplicates()
            filas += [[var, int(r.anio), int(r.mes), r.estado] for r in g.sort_values(["anio", "mes", "estado"]).itertuples()]
        return {"campos": {"variable": 0, "anio": 1, "mes": 2, "estado": 3}, "rangos": {}, "filas": filas}

    return _memo("disp_clima", fabrica)


def disponibilidad_sequia() -> dict:
    """[estado, año] con precipitación o temperatura registrada."""
    def fabrica():
        df = clima_df()
        sub = df[df[["precip", "tmax", "tmin"]].notna().any(axis=1)]
        g = sub.assign(anio=sub["fecha"].dt.year)[["estado", "anio"]].drop_duplicates().sort_values(["estado", "anio"])
        return {"campos": {"estado": 0, "anio_desde": 1, "anio_hasta": 1},
                "rangos": {"anio_desde": "desde", "anio_hasta": "hasta"},
                "filas": [[r.estado, int(r.anio)] for r in g.itertuples()]}

    return _memo("disp_sequia", fabrica)


def disponibilidad_comparacion() -> dict:
    """[producto, estado, variable] con al menos una semana comparada (precio y la variable)."""
    def fabrica():
        from .analitica import clima_semanal_estado, serie_precio_semanal_por_estado, unir_precio_clima

        p, c = precios_df(), clima_df()
        filas = []
        for producto, estados in estados_comparables().items():
            for estado in estados:
                unido, _ = unir_precio_clima(serie_precio_semanal_por_estado(p, producto, estado),
                                             clima_semanal_estado(c, estado))
                for var in ("TMAX", "TMIN", "PRECIP"):
                    if not unido.empty and unido[var.lower()].notna().any():
                        filas.append([producto, estado, var])
        return {"campos": {"producto": 0, "estado": 1, "variable": 2}, "rangos": {}, "filas": filas}

    return _memo("disp_comparacion", fabrica)


def combinacion_disponible(disp: dict, valores: dict) -> bool:
    """True si existe una fila con datos compatible con los valores no vacíos."""
    restricciones = []
    for campo, v in valores.items():
        if v in (None, "") or campo not in disp["campos"]:
            continue
        restricciones.append((disp["campos"][campo], disp["rangos"].get(campo), str(v)))
    for fila in disp["filas"]:
        ok = True
        for col, rango, v in restricciones:
            x = fila[col]
            if rango == "desde":
                ok = int(x) >= int(v)
            elif rango == "hasta":
                ok = int(x) <= int(v)
            else:
                ok = str(x) == v
            if not ok:
                break
        if ok:
            return True
    return False
