from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path
from api.admin import user_uuids_admin_view


def vendor_uuid_admin_view(request):
    return redirect("admin:api_vendor_changelist")


def delivery_staff_uuid_admin_view(request):
    return redirect("admin:api_deliverystaff_changelist")


urlpatterns = [
    path("admin/user-uuids/", admin.site.admin_view(user_uuids_admin_view), name="admin-user-uuids"),
    path("admin/vendor-id/", admin.site.admin_view(vendor_uuid_admin_view), name="admin-vendor-uuids"),
    path("admin/delivery-staff-id/", admin.site.admin_view(delivery_staff_uuid_admin_view), name="admin-delivery-staff-uuids"),
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]
