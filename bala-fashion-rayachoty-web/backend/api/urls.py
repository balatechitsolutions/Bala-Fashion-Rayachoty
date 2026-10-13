from django.urls import path
from . import views
from . import delivery
from . import addresses
from . import delivery_verification

urlpatterns = [
    path("health/", views.health),
    path("categories/", views.categories),
    path("categories/manage/", views.manage_category),
    path("vendors/manage/", views.manage_vendors),
    path("products/", views.products),
    path("profile/", views.profile),
    path("addresses/", addresses.customer_addresses),
    path("users/manage/", views.manage_auth_users),
    path("orders/", views.orders),
    path("delivery/quote/", views.delivery_quote),
    path("delivery/staff/", delivery.delivery_staff),
    path("delivery/availability/", delivery.delivery_availability),
    path("delivery/assign/", delivery.assign_delivery_staff),
    path("delivery/orders/", delivery.my_delivery_orders),
    path("delivery/location/", delivery.delivery_location),
    path("delivery/verify/", delivery_verification.delivery_verification),
    path("orders/manage/", views.manage_orders),
    path("notifications/", views.account_notifications),
    path("uploads/signature/", views.upload_signature),
    path("products/manage/", views.manage_product),
    path("seller/dashboard/", views.seller_dashboard),
]
