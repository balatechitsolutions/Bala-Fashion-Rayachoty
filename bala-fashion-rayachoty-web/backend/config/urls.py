from django.contrib import admin
from django.urls import include, path
from api.views import manage_vendors

urlpatterns = [
    # Keep this exact endpoint before Django Admin's catch-all route.
    path("admin/vendor-id/", manage_vendors, name="admin-vendor-id"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]
