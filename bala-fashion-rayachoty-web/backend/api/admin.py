from django.contrib import admin
from .models import Category, Product, Vendor


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("sort_order", "name")


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "phone", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug", "phone", "address")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "stock_quantity", "category", "vendor", "is_active")
    list_filter = ("is_active", "category", "vendor")
    search_fields = ("name", "slug", "description", "sku")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("category", "vendor")
    list_editable = ("price", "stock_quantity", "is_active")
    readonly_fields = ("created_at", "updated_at")
