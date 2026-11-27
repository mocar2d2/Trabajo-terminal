from django.urls import path

from . import views

app_name = "agro"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("precios/", views.precios, name="precios"),
    path("clima/", views.clima, name="clima"),
    path("prediccion/", views.prediccion, name="prediccion"),
    path("analisis/", views.eda, name="eda"),
    path("sequia/", views.sequia, name="sequia"),
    path("comparar/", views.comparar, name="comparar"),
    path("metodologia/", views.metodologia, name="metodologia"),
    path("salud/", views.salud, name="salud"),
    path("favicon.ico", views.favicon, name="favicon"),
]
