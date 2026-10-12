from django.contrib import admin, messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, connection, transaction
from django.shortcuts import redirect, render
import uuid
from django.urls import include, path

from api.views import manage_vendors


def _is_admin_superuser(request):
    if not request.user.is_superuser:
        raise PermissionDenied


@staff_member_required
def auth_user_uuids(request):
    """Shared searchable list of existing Supabase Auth users for vendor and delivery workflows."""
    _is_admin_superuser(request)
    auth_users = []
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.email, COALESCE(u.raw_user_meta_data->>'full_name', '') AS full_name,
                       u.created_at, COALESCE(p.role, 'customer') AS role
                FROM auth.users u
                LEFT JOIN public.profiles p ON p.id = u.id
                ORDER BY u.created_at DESC
                LIMIT 1000
                """
            )
            columns = [column[0] for column in cursor.description]
            auth_users = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except DatabaseError:
        messages.error(
            request,
            "Could not fetch website users from Supabase Auth. Verify Render DATABASE_URL permissions and the auth.users/public.profiles tables.",
        )
    return render(
        request,
        "admin/auth_user_uuids.html",
        {"title": "Website User UUIDs", "auth_users": auth_users},
    )


@staff_member_required
def vendor_uuids(request):
    """List vendor/store UUIDs and securely link each store to its Supabase Auth owner."""
    if not (request.user.is_superuser or request.user.has_perm("api.view_vendor")):
        raise PermissionDenied

    if request.method == "POST":
        _is_admin_superuser(request)
        vendor_id_raw = request.POST.get("vendor_id", "").strip()
        owner_id_raw = request.POST.get("owner_user_id", "").strip()
        try:
            vendor_id = str(uuid.UUID(vendor_id_raw))
            owner_id = str(uuid.UUID(owner_id_raw))
        except (ValueError, TypeError, AttributeError):
            messages.error(request, "Enter valid vendor and Supabase Auth UUIDs.")
            return redirect("admin-vendor-uuids")

        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT id, name FROM public.vendors WHERE id = %s FOR UPDATE", [vendor_id])
                    vendor = cursor.fetchone()
                    if not vendor:
                        messages.error(request, "Vendor record not found.")
                        return redirect("admin-vendor-uuids")

                    cursor.execute(
                        "SELECT id, COALESCE(raw_user_meta_data->>'full_name', '') FROM auth.users WHERE id = %s",
                        [owner_id],
                    )
                    auth_user = cursor.fetchone()
                    if not auth_user:
                        messages.error(
                            request,
                            "No Supabase Auth user exists for that UUID. Create the account in Supabase Authentication → Users first.",
                        )
                        return redirect("admin-vendor-uuids")

                    cursor.execute("SELECT role FROM public.profiles WHERE id = %s", [owner_id])
                    profile = cursor.fetchone()
                    if profile and profile[0] == "admin":
                        messages.error(request, "An admin account cannot be assigned as a vendor owner. Use a separate vendor account.")
                        return redirect("admin-vendor-uuids")
                    if profile and profile[0] == "delivery_boy":
                        messages.error(request, "A delivery staff account cannot also be a vendor owner. Use a separate vendor account.")
                        return redirect("admin-vendor-uuids")

                    cursor.execute(
                        "SELECT id FROM public.vendors WHERE owner_id = %s AND id <> %s LIMIT 1",
                        [owner_id, vendor_id],
                    )
                    other_vendor = cursor.fetchone()
                    if other_vendor:
                        messages.error(request, "This Supabase user already owns another vendor record. Use the existing store or a different account.")
                        return redirect("admin-vendor-uuids")

                    cursor.execute(
                        """INSERT INTO public.profiles (id, full_name, role)
                           VALUES (%s, %s, 'vendor')
                           ON CONFLICT (id) DO UPDATE SET
                             full_name = CASE
                               WHEN COALESCE(public.profiles.full_name, '') = ''
                                    AND EXCLUDED.full_name <> ''
                               THEN EXCLUDED.full_name
                               ELSE public.profiles.full_name
                             END,
                             role = 'vendor',
                             updated_at = now()""",
                        [owner_id, str(auth_user[1] or "")[:120]],
                    )
                    cursor.execute(
                        "UPDATE public.vendors SET owner_id = %s WHERE id = %s",
                        [owner_id, vendor_id],
                    )
            messages.success(request, f"Linked Supabase Auth user to vendor '{vendor[1]}'. The owner UUID is now saved.")
        except DatabaseError:
            messages.error(
                request,
                "Could not link the owner. Verify that public.vendors.owner_id references the Supabase Auth user UUID and that public.profiles has the expected columns.",
            )
        return redirect("admin-vendor-uuids")

    vendors = []
    auth_users = []
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
            # The owner must already exist in Supabase Auth (normally after website sign-in).
            # Show email next to Auth UUID so an admin can match the vendor's email correctly.
            cursor.execute(
                """
                SELECT id, email, COALESCE(raw_user_meta_data->>'full_name', '') AS full_name, created_at
                FROM auth.users
                ORDER BY created_at DESC
                LIMIT 1000
                """
            )
            columns = [column[0] for column in cursor.description]
            auth_users = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except DatabaseError:
        messages.error(
            request,
            "Could not load vendor or Supabase Auth users from the connected database. "
            "Verify Render DATABASE_URL permissions and the public.vendors/auth.users tables.",
        )

    return render(
        request,
        "admin/vendor_uuids.html",
        {"title": "Vendor Owner UUIDs", "vendors": vendors, "auth_users": auth_users},
    )


@staff_member_required
def delivery_staff_uuids(request):
    """Manage delivery staff from Supabase-backed profiles; no Django model/table."""
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
                    "SELECT id, email, COALESCE(raw_user_meta_data->>'full_name', '') FROM auth.users WHERE id = %s",
                    [staff_id],
                )
                auth_user = cursor.fetchone()
                if not auth_user:
                    messages.error(request, "No Supabase Auth user exists for that UUID. The delivery staff member must first register or sign in on the website.")
                    return redirect("admin-delivery-staff-uuids")
                cursor.execute("SELECT role FROM public.profiles WHERE id = %s", [staff_id])
                existing_profile = cursor.fetchone()
                if existing_profile and existing_profile[0] in {"admin", "vendor"}:
                    messages.error(request, "This account already has an admin/vendor role. Select a separate customer account for delivery work.")
                    return redirect("admin-delivery-staff-uuids")
                if existing_profile and existing_profile[0] == "delivery_boy":
                    messages.info(request, "This user is already authorized as delivery staff.")
                    return redirect("admin-delivery-staff-uuids")
                cursor.execute(
                    """INSERT INTO public.profiles (id, full_name, phone, role)
                       VALUES (%s, %s, %s, 'delivery_boy')
                       ON CONFLICT (id) DO UPDATE SET
                         full_name = CASE WHEN EXCLUDED.full_name <> '' THEN EXCLUDED.full_name ELSE public.profiles.full_name END,
                         phone = CASE WHEN EXCLUDED.phone <> '' THEN EXCLUDED.phone ELSE public.profiles.phone END,
                         role = 'delivery_boy',
                         updated_at = now()""",
                    [staff_id, full_name or str(auth_user[2] or "")[:120], phone],
                )
            messages.success(request, "Delivery staff authorized successfully. The Supabase Auth UUID is now enabled for delivery assignments.")
        except DatabaseError:
            messages.error(request, "Could not authorize delivery staff. Verify the Supabase database connection and apply the delivery-role SQL migration.")
        return redirect("admin-delivery-staff-uuids")

    staff = []
    auth_users = []
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT p.id, p.full_name, p.phone, p.updated_at, u.email
                FROM public.profiles p
                LEFT JOIN auth.users u ON u.id = p.id
                WHERE p.role = %s
                ORDER BY p.full_name ASC NULLS LAST, p.id ASC
                LIMIT 500
                """,
                ["delivery_boy"],
            )
            columns = [column[0] for column in cursor.description]
            staff = [dict(zip(columns, row)) for row in cursor.fetchall()]
            # List existing website/Auth users so admins can select the matching email and copy UUID.
            cursor.execute(
                """
                SELECT u.id, u.email, COALESCE(u.raw_user_meta_data->>'full_name', '') AS full_name,
                       u.created_at, COALESCE(p.role, 'customer') AS role
                FROM auth.users u
                LEFT JOIN public.profiles p ON p.id = u.id
                ORDER BY u.created_at DESC
                LIMIT 1000
                """
            )
            columns = [column[0] for column in cursor.description]
            auth_users = [dict(zip(columns, row)) for row in cursor.fetchall()]
    except DatabaseError:
        messages.error(
            request,
            "Could not load delivery staff or Supabase Auth users. Verify Render DATABASE_URL permissions and the public.profiles/auth.users tables.",
        )

    return render(
        request,
        "admin/delivery_staff_uuids.html",
        {"title": "Delivery Staff Management", "delivery_staff": staff, "auth_users": auth_users},
    )


urlpatterns = [
    # Keep custom admin routes before Django Admin's catch-all route.
    path("admin/vendor-id/", manage_vendors, name="admin-vendor-id"),
    path("admin/auth-user-uuids/", auth_user_uuids, name="admin-auth-user-uuids"),
    path("admin/vendor-uuids/", vendor_uuids, name="admin-vendor-uuids"),
    path("admin/delivery-staff-uuids/", delivery_staff_uuids, name="admin-delivery-staff-uuids"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]
