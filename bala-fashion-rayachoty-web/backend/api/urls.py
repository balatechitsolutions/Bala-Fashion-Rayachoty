from django.urls import path
from . import views
urlpatterns = [
 path("health/",views.health),
 path("categories/",views.categories),
 path("categories/manage/",views.manage_category),
 path("products/",views.products),
 path("profile/",views.profile),
 path("orders/",views.orders),
 path("uploads/signature/",views.upload_signature),
 path("products/manage/",views.manage_product),
]
