from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import DatabaseError, connection
from django.shortcuts import render
from django.urls import include, path
from django.core.exceptions import PermissionDenied

from api.views import manage_vendors


@staff_member_required
def vendor_uuids(request):
    """Read-only staff page showing vendor record UUIDs and Supabase Auth owner UUIDs."""
    if not (request.user.is_superuser or request.user.has_perm("api.view_vendor")):
        raise PermissionDenied

    vendors = []
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, name, owner_id, status, phone, created_at
                FROM public.vendors
                ORDER BY name ASC
                """
            )
            columns = [column[0] for column in cursor.description]
            vendors = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except DatabaseError:
        messages.error(
            request,
            "Could not load vendor UUIDs from the connected database. "
            "Verify the Render DATABASE_URL and public.vendors table.",
        )

    return render(
        request,
        "admin/vendor_uuids.html",
        {"title": "Vendor UUIDs", "vendors": vendors},
    )


urlpatterns = [
    # Keep this exact endpoint before Django Admin's catch-all route.
    path("admin/vendor-id/", manage_vendors, name="admin-vendor-id"),
    path("admin/vendor-uuids/", vendor_uuids, name="admin-vendor-uuids"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]
