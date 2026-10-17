from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path


def vendor_uuid_admin_view(request):
    # Keep the existing Django admin authentication and permissions.
    return redirect("admin:api_vendor_changelist")


urlpatterns = [
    path(
        "admin/vendor-id/",
        admin.site.admin_view(vendor_uuid_admin_view),
        name="admin-vendor-uuids",
    ),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]
