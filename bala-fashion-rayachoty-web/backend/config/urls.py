from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, connection
from django.shortcuts import redirect, render
import uuid
from django.urls import include, path

from api.views import manage_vendors


def _is_admin_superuser(request):
    if not request.user.is_superuser:
        raise PermissionDenied


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


@staff_member_required
def delivery_staff_uuids(request):
    """Read-only list of delivery staff from Supabase-backed profiles; no Django model/table."""
    _is_admin_superuser(request)

    if request.method == "POST":
        staff_id_raw = request.POST.get("user_id", "").strip()
        full_name = request.POST.get("full_name", "").strip()[:120]
        phone = request.POST.get("phone", "").strip()[:30]
        try:
            staff_id = str(uuid.UUID(staff_id_raw))
        except (ValueError, TypeError, AttributeError):
            messages.error(request, "Enter a valid Supabase Auth UUID copied from Supabase Authentication → Users.")
            return redirect("admin-delivery-staff-uuids")

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id, COALESCE(raw_user_meta_data->>'full_name', '') FROM auth.users WHERE id = %s",
                    [staff_id],
                )
                auth_user = cursor.fetchone()
                if not auth_user:
                    messages.error(request, "No Supabase Auth user exists for that UUID. Create the user in Supabase Authentication first.")
                    return redirect("admin-delivery-staff-uuids")
                cursor.execute("SELECT role FROM public.profiles WHERE id = %s", [staff_id])
                existing_profile = cursor.fetchone()
                if existing_profile and existing_profile[0] in {"admin", "vendor"}:
                    messages.error(request, "This account already has an admin/vendor role. Use a separate customer account for delivery work.")
                    return redirect("admin-delivery-staff-uuids")
                cursor.execute(
                    """INSERT INTO public.profiles (id, full_name, phone, role)
                       VALUES (%s, %s, %s, 'delivery_boy')
                       ON CONFLICT (id) DO UPDATE SET
                         full_name = CASE WHEN EXCLUDED.full_name <> '' THEN EXCLUDED.full_name ELSE public.profiles.full_name END,
                         phone = CASE WHEN EXCLUDED.phone <> '' THEN EXCLUDED.phone ELSE public.profiles.phone END,
                         role = 'delivery_boy',
                         updated_at = now()""",
                    [staff_id, full_name or str(auth_user[1] or "")[:120], phone],
                )
            messages.success(request, "Delivery staff authorized successfully. The Supabase Auth UUID is now enabled for delivery assignments.")
        except DatabaseError:
            messages.error(request, "Could not authorize delivery staff. Verify the Supabase database connection and apply the delivery-role SQL migration.")
        return redirect("admin-delivery-staff-uuids")

    staff = []
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, full_name, phone, updated_at
                FROM public.profiles
                WHERE role = %s
                ORDER BY full_name ASC NULLS LAST, id ASC
                LIMIT 500
                """,
                ["delivery_boy"],
            )
            columns = [column[0] for column in cursor.description]
            staff = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except DatabaseError:
        messages.error(
            request,
            "Could not load delivery staff UUIDs. Verify that the connected database "
            "is Supabase PostgreSQL and that the public.profiles delivery_boy role is configured.",
        )

    return render(
        request,
        "admin/delivery_staff_uuids.html",
        {"title": "Delivery Staff Management", "delivery_staff": staff},
    )


urlpatterns = [
    # Keep custom admin routes before Django Admin's catch-all route.
    path("admin/vendor-id/", manage_vendors, name="admin-vendor-id"),
    path("admin/vendor-uuids/", vendor_uuids, name="admin-vendor-uuids"),
    path("admin/delivery-staff-uuids/", delivery_staff_uuids, name="admin-delivery-staff-uuids"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]
