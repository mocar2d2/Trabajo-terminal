from django.urls import include, path

urlpatterns = [
    path("", include("agro.urls")),
]

handler404 = "agro.views.error_404"
handler500 = "agro.views.error_500"
