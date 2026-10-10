import os

import requests
from django import forms
from django.contrib import admin, messages
from django.shortcuts import render
from django.urls import path
from django.core.exceptions import ValidationError
from django.utils.html import format_html
import cloudinary
import cloudinary.uploader

from .models import Category, Product, Vendor


# Store-specific Django admin branding.
admin.site.site_header = "Bala Fashion Rayachoty"
admin.site.site_title = "Bala Fashion Admin"
admin.site.index_title = "Store management dashboard"


class CloudinaryUploadFormMixin:
    """Adds a real file picker while keeping image URLs in the existing database columns."""

    def _validate_upload(self, uploaded_file):
        if not uploaded_file:
            return
        if not uploaded_file.content_type or not uploaded_file.content_type.startswith("image/"):
            raise ValidationError("Choose a valid image file.")
        if uploaded_file.size > 8 * 1024 * 1024:
            raise ValidationError("Image must be 8 MB or smaller.")


class CategoryAdminForm(CloudinaryUploadFormMixin, forms.ModelForm):
    image_upload = forms.FileField(
        required=False,
        label="Upload category image",
        help_text="Choose an image to upload to Cloudinary. Maximum 8 MB.",
    )

    class Meta:
        model = Category
        fields = "__all__"

    def clean_image_upload(self):
        image = self.cleaned_data.get("image_upload")
        self._validate_upload(image)
        return image


class ProductAdminForm(CloudinaryUploadFormMixin, forms.ModelForm):
    sizes_text = forms.CharField(required=False, label="Sizes (comma separated)", widget=forms.TextInput(attrs={"placeholder": "S, M, L, XL"}))
    colors_text = forms.CharField(required=False, label="Colours (comma separated)", widget=forms.TextInput(attrs={"placeholder": "Black, White, Blue"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["sizes_text"].initial = ", ".join(self.instance.sizes or [])
            self.fields["colors_text"].initial = ", ".join(self.instance.colors or [])

    def clean(self):
        cleaned = super().clean()
        for source, target in (("sizes_text", "sizes"), ("colors_text", "colors")):
            cleaned[target] = list(dict.fromkeys(v.strip() for v in cleaned.get(source, "").split(",") if v.strip()))
        if cleaned.get("stock_quantity") is not None and cleaned["stock_quantity"] < 0:
            self.add_error("stock_quantity", "Stock cannot be negative.")
        if cleaned.get("price") is not None and cleaned["price"] < 0:
            self.add_error("price", "Price cannot be negative.")
        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.sizes = self.cleaned_data["sizes"]
        obj.colors = self.cleaned_data["colors"]
        if commit:
            obj.save()
            self.save_m2m()
        return obj


    image_upload = forms.FileField(
        required=False,
        label="Upload product image",
        help_text="Choose an image to upload to Cloudinary. Maximum 8 MB.",
    )

    class Meta:
        model = Product
        fields = "__all__"

    def clean_image_upload(self):
        image = self.cleaned_data.get("image_upload")
        self._validate_upload(image)
        return image


class VendorAdminForm(CloudinaryUploadFormMixin, forms.ModelForm):
    logo_upload = forms.FileField(
        required=False,
        label="Upload vendor logo",
        help_text="Choose a logo to upload to Cloudinary. Maximum 8 MB.",
    )

    class Meta:
        model = Vendor
        fields = "__all__"

    def clean_logo_upload(self):
        image = self.cleaned_data.get("logo_upload")
        self._validate_upload(image)
        return image


class CloudinaryUploadAdminMixin:
    upload_field = None
    url_field = None
    public_id_field = None
    upload_folder = None

    def save_model(self, request, obj, form, change):
        uploaded = form.cleaned_data.get(self.upload_field) if self.upload_field else None
        if uploaded:
            cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "")
            api_key = os.getenv("CLOUDINARY_API_KEY", "")
            api_secret = os.getenv("CLOUDINARY_API_SECRET", "")
            if not all((cloud_name, api_key, api_secret)):
                self.message_user(
                    request,
                    "Image upload is unavailable: configure CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET on Render.",
                    level=messages.ERROR,
                )
                raise ValidationError("Cloudinary credentials are not configured.")
            cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)
            result = cloudinary.uploader.upload(
                uploaded,
                folder=self.upload_folder,
                resource_type="image",
                allowed_formats=["jpg", "jpeg", "png", "webp", "gif"],
            )
            setattr(obj, self.url_field, result["secure_url"])
            if self.public_id_field:
                setattr(obj, self.public_id_field, result["public_id"])
        super().save_model(request, obj, form, change)


@admin.register(Category)
class CategoryAdmin(CloudinaryUploadAdminMixin, admin.ModelAdmin):
    form = CategoryAdminForm
    upload_field = "image_upload"
    url_field = "image_url"
    upload_folder = "bala-fashion/categories"
    list_display = ("thumbnail", "name", "sort_order", "is_active", "image_status")
    list_display_links = ("name",)
    list_editable = ("sort_order", "is_active")
    list_per_page = 25
    save_on_top = True
    actions = ("activate", "deactivate")
    list_filter = ("is_active", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("sort_order", "name")
    readonly_fields = ("image_preview", "created_at")
    fieldsets = (
        ("Category details", {"fields": ("name", "slug", "sort_order", "is_active")}),
        ("Category image", {"fields": ("image_upload", "image_preview", "image_url")}),
        ("Record information", {"fields": ("created_at",)}),
    )

    @admin.display(description="Preview")
    def thumbnail(self, obj):
        return format_html('<img src="{}" class="bf-thumbnail" alt="">', obj.image_url) if obj.image_url else "—"

    @admin.action(description="Activate selected categories")
    def activate(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=True)} categories activated.")

    @admin.action(description="Deactivate selected categories")
    def deactivate(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=False)} categories deactivated.")

    @admin.display(description="Image")
    def image_status(self, obj):
        return "Uploaded" if obj.image_url else "Missing"

    @admin.display(description="Current image")
    def image_preview(self, obj):
        if obj and obj.image_url:
            from django.utils.html import format_html
            return format_html('<a href="{}" target="_blank" rel="noopener">Open current image</a>', obj.image_url)
        return "No image uploaded"


@admin.register(Vendor)
class VendorAdmin(CloudinaryUploadAdminMixin, admin.ModelAdmin):
    form = VendorAdminForm
    upload_field = "logo_upload"
    url_field = "logo_url"
    upload_folder = "bala-fashion/vendor-logos"
    list_display = ("thumbnail", "name", "status", "phone", "created_at")
    list_display_links = ("name",)
    list_editable = ("status",)
    list_per_page = 25
    save_on_top = True
    actions = ("approve", "suspend")
    list_filter = ("status", "created_at")
    search_fields = ("name", "slug", "phone", "address")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at",)
    fieldsets = (
        ("Vendor details", {"fields": ("name", "slug", "owner_id", "status")}),
        ("Contact information", {"fields": ("phone", "address", "description")}),
        ("Branding", {"fields": ("logo_upload", "logo_url")}),
        ("Record information", {"fields": ("created_at",)}),
    )

    @admin.display(description="Logo")
    def thumbnail(self, obj):
        return format_html('<img src="{}" class="bf-thumbnail" alt="">', obj.logo_url) if obj.logo_url else "—"

    @admin.action(description="Approve selected vendors")
    def approve(self, request, queryset):
        self.message_user(request, f"{queryset.update(status='approved')} vendors approved.")

    @admin.action(description="Suspend selected vendors")
    def suspend(self, request, queryset):
        self.message_user(request, f"{queryset.update(status='suspended')} vendors suspended.")


@admin.register(Product)
class ProductAdmin(CloudinaryUploadAdminMixin, admin.ModelAdmin):
    form = ProductAdminForm
    upload_field = "image_upload"
    url_field = "image_url"
    public_id_field = "image_public_id"
    upload_folder = "bala-fashion/products"
    list_display = ("thumbnail", "name", "price", "stock_quantity", "category", "vendor", "is_active", "image_status")
    list_display_links = ("name",)
    list_per_page = 25
    save_on_top = True
    actions = ("publish", "hide", "zero_stock")
    list_filter = ("is_active", "category", "vendor", "created_at")
    search_fields = ("name", "slug", "description", "sku")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("category", "vendor")
    list_editable = ("price", "stock_quantity", "is_active")
    list_select_related = ("category", "vendor")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Product details", {"fields": ("name", "slug", "vendor", "category", "sku", "description")}),
        ("Pricing & inventory", {"fields": ("price", "compare_at_price", "stock_quantity", "sizes_text", "colors_text")}),
        ("Product image", {"fields": ("image_upload", "image_url", "image_public_id")}),
        ("Store visibility", {"fields": ("is_active",)}),
        ("Record information", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Preview")
    def thumbnail(self, obj):
        return format_html('<img src="{}" class="bf-thumbnail" alt="">', obj.image_url) if obj.image_url else "—"

    @admin.action(description="Publish selected products")
    def publish(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=True)} products published.")

    @admin.action(description="Hide selected products")
    def hide(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=False)} products hidden.")

    @admin.action(description="Set selected products stock to zero")
    def zero_stock(self, request, queryset):
        self.message_user(request, f"{queryset.update(stock_quantity=0)} products updated.")

    @admin.display(description="Image")
    def image_status(self, obj):
        return "Uploaded" if obj.image_url else "Missing"


# Read-only Supabase Auth user directory. These are the identities referenced by
# public.vendors.owner_id; they are not Django's local staff-user records.
def supabase_auth_users_view(request):
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    page = request.GET.get("page", "1")
    try:
        page = max(1, min(int(page), 10000))
    except (TypeError, ValueError):
        page = 1

    context = {
        **admin.site.each_context(request),
        "title": "Supabase Auth users",
        "users": [],
        "page_number": page,
        "has_previous": page > 1,
        "previous_page": page - 1,
        "next_page": page + 1,
        "error": "",
        "has_next": False,
    }
    if not supabase_url or not service_key:
        context["error"] = (
            "User UUIDs are stored in Supabase Auth. Configure SUPABASE_SERVICE_ROLE_KEY "
            "and SUPABASE_URL in the Render backend environment to load this directory."
        )
        return render(request, "admin/supabase_users.html", context)

    try:
        response = requests.get(
            f"{supabase_url}/auth/v1/admin/users",
            params={"page": page, "per_page": 50},
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        users = payload.get("users", []) if isinstance(payload, dict) else []
        context["users"] = [
            {
                "id": str(user.get("id", "")),
                "email": user.get("email") or "—",
                "phone": user.get("phone") or "—",
                "created_at": user.get("created_at") or "—",
                "last_sign_in_at": user.get("last_sign_in_at") or "—",
                "email_confirmed": bool(user.get("email_confirmed_at")),
            }
            for user in users
            if user.get("id")
        ]
        context["has_next"] = len(users) == 50
    except (requests.RequestException, ValueError, TypeError):
        context["error"] = (
            "Supabase Auth users could not be loaded. Verify the service-role secret, "
            "Supabase URL, and backend network access."
        )
        context["has_next"] = False
    return render(request, "admin/supabase_users.html", context)


# Add a staff-only admin page without altering Django's default User model or IDs.
_original_admin_get_urls = admin.site.get_urls

def _admin_get_urls_with_supabase_users():
    custom_urls = [
        path(
            "supabase-users/",
            admin.site.admin_view(supabase_auth_users_view),
            name="supabase_users",
        ),
    ]
    return custom_urls + _original_admin_get_urls()

admin.site.get_urls = _admin_get_urls_with_supabase_users
