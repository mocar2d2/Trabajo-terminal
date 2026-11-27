"""Formularios de filtros. Las opciones provienen exclusivamente de los datos."""
from django import forms

from .configuracion import MESES, VARIABLES_CLIMA, nombre_publico

SIN_COMBINACION = "No hay información disponible para la combinación seleccionada. Elija otra combinación de filtros."


def _opciones_productos(productos):
    """Productos agrupados por cultivo (optgroup) con su nombre público; el valor enviado
    es el nombre original del producto."""
    grupos = {}
    for p in productos:
        grupos.setdefault(p["cultivo"], []).append((p["producto"], nombre_publico(p["producto"])))
    return list(grupos.items())


def _opciones(valores, vacio=None):
    op = [(str(v), str(v)) for v in valores]
    return ([("", vacio)] + op) if vacio else op


class FormularioBase(forms.Form):
    """disponibilidad: combinaciones con datos (consultas.disponibilidad_*). Se usan en el
    navegador para ofrecer solo opciones compatibles y aquí para validar lo recibido."""

    def __init__(self, *args, disponibilidad=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.disponibilidad = disponibilidad
        for campo in self.fields.values():
            campo.widget.attrs.setdefault("class", "control")

    def clean(self):
        datos = super().clean()
        if self.disponibilidad and not self.errors:
            from .servicios.consultas import combinacion_disponible

            valores = {c: datos.get(c) for c in self.disponibilidad["campos"]}
            if not combinacion_disponible(self.disponibilidad, valores):
                raise forms.ValidationError(SIN_COMBINACION, code="sin_combinacion")
        return datos


def _validar_rango(form, desde="anio_desde", hasta="anio_hasta"):
    d = form.cleaned_data.get(desde)
    h = form.cleaned_data.get(hasta)
    if d and h and int(d) > int(h):
        raise forms.ValidationError("El año inicial no puede ser posterior al año final. Seleccione un intervalo válido.")


class FiltroPrecios(FormularioBase):
    producto = forms.ChoiceField(label="Producto")
    estado = forms.ChoiceField(label="Estado de origen", required=False)
    presentacion = forms.ChoiceField(label="Presentación", required=False)
    anio_desde = forms.ChoiceField(label="Desde el año", required=False)
    anio_hasta = forms.ChoiceField(label="Hasta el año", required=False)

    def __init__(self, *args, productos=(), opciones=None, **kwargs):
        super().__init__(*args, **kwargs)
        opciones = opciones or {"estados": [], "presentaciones": [], "anios": []}
        self.fields["producto"].choices = _opciones_productos(productos)
        self.fields["estado"].choices = _opciones(opciones["estados"], "Todos los orígenes")
        self.fields["presentacion"].choices = _opciones(opciones["presentaciones"], "Todas")
        # Los granos no tienen presentación en la fuente: un selector con solo «Todas» no
        # aporta nada, así que se oculta (el navegador lo muestra u oculta al cambiar de producto).
        self.fields["presentacion"].widget.attrs["data-ocultar-sin-opciones"] = "1"
        self.fields["presentacion"].oculto = not opciones["presentaciones"]
        self.fields["anio_desde"].choices = _opciones(opciones["anios"], "Primer año disponible")
        self.fields["anio_hasta"].choices = _opciones(opciones["anios"], "Último año disponible")

    def clean(self):
        _validar_rango(self)
        return super().clean()


class FiltroProducto(FormularioBase):
    producto = forms.ChoiceField(label="Producto")

    def __init__(self, *args, productos=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["producto"].choices = _opciones_productos(productos)


class FiltroEDA(FiltroProducto):
    anio_desde = forms.ChoiceField(label="Desde el año", required=False)
    anio_hasta = forms.ChoiceField(label="Hasta el año", required=False)

    def __init__(self, *args, anios=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["anio_desde"].choices = _opciones(anios, "Primer año disponible")
        self.fields["anio_hasta"].choices = _opciones(anios, "Último año disponible")
        for c in ("anio_desde", "anio_hasta"):
            self.fields[c].widget.attrs["class"] = "control"

    def clean(self):
        _validar_rango(self)
        return super().clean()


class FiltroClima(FormularioBase):
    variable = forms.ChoiceField(
        label="Dato climático", choices=[(k, f"{v['etiqueta']} ({v['unidad']})") for k, v in VARIABLES_CLIMA.items()]
    )
    estado = forms.ChoiceField(label="Estado", required=False)
    anio = forms.ChoiceField(label="Año")
    mes = forms.ChoiceField(label="Mes", required=False)

    def __init__(self, *args, anios=(), estados=(), meses=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["anio"].choices = _opciones(anios)
        validos = set(meses) if meses is not None else {n for n, _ in MESES}
        self.fields["mes"].choices = [("", "Todo el año")] + [(str(n), m.capitalize()) for n, m in MESES if n in validos]
        self.fields["estado"].choices = _opciones(estados, "Todos los estados")


class FiltroSequia(FormularioBase):
    estado = forms.ChoiceField(label="Estado")
    anio_desde = forms.ChoiceField(label="Desde el año", required=False)
    anio_hasta = forms.ChoiceField(label="Hasta el año", required=False)

    def __init__(self, *args, anios=(), estados=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["estado"].choices = _opciones(estados)
        self.fields["anio_desde"].choices = _opciones(anios, "Primer año disponible")
        self.fields["anio_hasta"].choices = _opciones(anios, "Último año disponible")

    def clean(self):
        _validar_rango(self)
        return super().clean()


class FormularioComparacion(FormularioBase):
    """Formulario POST (protegido con CSRF)."""

    producto = forms.ChoiceField(label="Producto")
    estado = forms.ChoiceField(label="Estado de origen con datos climáticos")
    variable = forms.ChoiceField(
        label="Variable climática",
        choices=[(k, f"{v['etiqueta']} ({v['unidad']})") for k, v in VARIABLES_CLIMA.items()],
    )

    def __init__(self, *args, comparables=None, **kwargs):
        super().__init__(*args, **kwargs)
        comparables = comparables or {}
        self.comparables = comparables
        self.fields["producto"].choices = [(p, nombre_publico(p)) for p in sorted(comparables)]
        estados = sorted({e for lista in comparables.values() for e in lista})
        self.fields["estado"].choices = _opciones(estados)

    def clean(self):
        datos = super().clean()
        p, e = datos.get("producto"), datos.get("estado")
        if p and e and e not in self.comparables.get(p, []):
            raise forms.ValidationError(SIN_COMBINACION, code="sin_combinacion")
        return datos
