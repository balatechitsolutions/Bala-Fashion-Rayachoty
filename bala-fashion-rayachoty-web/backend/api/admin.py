import os

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
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
    list_display = ("name", "slug", "sort_order", "is_active", "image_status")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("sort_order", "name")
    readonly_fields = ("image_preview", "created_at")
    fieldsets = (
        ("Category details", {"fields": ("name", "slug", "sort_order", "is_active")}),
        ("Category image", {"fields": ("image_upload", "image_preview", "image_url")}),
        ("Record information", {"fields": ("created_at",)}),
    )

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
    list_display = ("name", "status", "phone", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug", "phone", "address")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at",)
    fieldsets = (
        ("Vendor details", {"fields": ("name", "slug", "owner_id", "status")}),
        ("Contact information", {"fields": ("phone", "address", "description")}),
        ("Branding", {"fields": ("logo_upload", "logo_url")}),
        ("Record information", {"fields": ("created_at",)}),
    )


@admin.register(Product)
class ProductAdmin(CloudinaryUploadAdminMixin, admin.ModelAdmin):
    form = ProductAdminForm
    upload_field = "image_upload"
    url_field = "image_url"
    public_id_field = "image_public_id"
    upload_folder = "bala-fashion/products"
    list_display = ("name", "price", "stock_quantity", "category", "vendor", "is_active", "image_status")
    list_filter = ("is_active", "category", "vendor")
    search_fields = ("name", "slug", "description", "sku")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("category", "vendor")
    list_editable = ("price", "stock_quantity", "is_active")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Product details", {"fields": ("name", "slug", "vendor", "category", "sku", "description")}),
        ("Pricing & inventory", {"fields": ("price", "compare_at_price", "stock_quantity", "sizes", "colors")}),
        ("Product image", {"fields": ("image_upload", "image_url", "image_public_id")}),
        ("Store visibility", {"fields": ("is_active",)}),
        ("Record information", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Image")
    def image_status(self, obj):
        return "Uploaded" if obj.image_url else "Missing"
