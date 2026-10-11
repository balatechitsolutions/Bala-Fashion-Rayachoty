import logging
import os

import requests
from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError
from django.utils.html import format_html
from django.utils.text import slugify
import cloudinary
import cloudinary.exceptions
import cloudinary.uploader

from .models import Category, Product, Vendor

logger = logging.getLogger(__name__)


# Store-specific Django admin branding.
admin.site.site_header = "Bala Fashion Rayachoty"
admin.site.site_title = "Bala Fashion Admin"
admin.site.index_title = "Store management dashboard"
admin.site.index_template = "admin/custom_index.html"


class CloudinaryUploadFormMixin:
    """Adds a real file picker while keeping image URLs in the existing database columns."""

    def _validate_upload(self, uploaded_file):
        if not uploaded_file:
            return
        content_type = getattr(uploaded_file, "content_type", "") or ""
        if not content_type.startswith("image/"):
            raise ValidationError("Choose a valid image file.")
        if uploaded_file.size > 8 * 1024 * 1024:
            raise ValidationError("Image must be 8 MB or smaller.")
        if not all(os.getenv(key, "").strip() for key in (
            "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"
        )):
            raise ValidationError(
                "Image upload is not configured. Add CLOUDINARY_CLOUD_NAME, "
                "CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET to the Render environment."
            )


def _unique_slug(model, name, current_pk=None):
    """Return a URL-safe, unused slug; database uniqueness remains the final guard."""
    base = slugify((name or "").strip())[:220] or "item"
    candidate = base
    suffix = 2
    queryset = model.objects.all()
    if current_pk:
        queryset = queryset.exclude(pk=current_pk)
    while queryset.filter(slug=candidate).exists():
        tail = f"-{suffix}"
        candidate = f"{base[:255 - len(tail)]}{tail}"
        suffix += 1
    return candidate


class CategoryAdminForm(CloudinaryUploadFormMixin, forms.ModelForm):
    image_upload = forms.FileField(
        required=False,
        label="Upload category image",
        help_text="Choose an image to upload to Cloudinary. Maximum 8 MB.",
    )

    class Meta:
        model = Category
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        name = (cleaned.get("name") or "").strip()
        slug = (cleaned.get("slug") or "").strip()
        if name:
            if not slug:
                cleaned["slug"] = _unique_slug(Category, name, self.instance.pk)
            elif Category.objects.filter(slug=slug).exclude(pk=self.instance.pk).exists():
                self.add_error("slug", "This slug is already used. Choose another slug.")
            if Category.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
                self.add_error("name", "A category with this name already exists.")
        return cleaned

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
        price = cleaned.get("price")
        compare_at_price = cleaned.get("compare_at_price")
        if price is not None and price < 0:
            self.add_error("price", "Price cannot be negative.")
        if compare_at_price is not None and compare_at_price < 0:
            self.add_error("compare_at_price", "Compare-at price cannot be negative.")
        if price is not None and compare_at_price is not None and compare_at_price < price:
            self.add_error("compare_at_price", "Compare-at price must be greater than or equal to the selling price.")
        name = (cleaned.get("name") or "").strip()
        slug = (cleaned.get("slug") or "").strip()
        if name:
            if not slug:
                cleaned["slug"] = _unique_slug(Product, name, self.instance.pk)
            elif Product.objects.filter(slug=slug).exclude(pk=self.instance.pk).exists():
                self.add_error("slug", "This slug is already used. Choose another slug.")
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

    def clean(self):
        cleaned = super().clean()

        # The Supabase Auth UUID is optional in the database. Never turn a
        # blank value into an invalid UUID or a Django staff-user integer.
        if not cleaned.get("owner_id"):
            cleaned["owner_id"] = None

        # Generate slugs server-side for mobile browsers and report duplicates
        # as form errors instead of allowing a database IntegrityError to escape.
        name = (cleaned.get("name") or "").strip()
        slug = (cleaned.get("slug") or "").strip()
        if name:
            if not slug:
                cleaned["slug"] = _unique_slug(Vendor, name, self.instance.pk)
            elif Vendor.objects.filter(slug=slug).exclude(pk=self.instance.pk).exists():
                self.add_error("slug", "This slug is already used. Choose another slug.")
        return cleaned

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
        uploaded_public_id = None
        if uploaded:
            cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
            api_key = os.getenv("CLOUDINARY_API_KEY", "").strip()
            api_secret = os.getenv("CLOUDINARY_API_SECRET", "").strip()
            if not all((cloud_name, api_key, api_secret)):
                raise ValidationError(
                    "Image upload is not configured. Set the three Cloudinary credentials on Render."
                )
            cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)
            result = cloudinary.uploader.upload(
                uploaded,
                folder=self.upload_folder,
                resource_type="image",
                allowed_formats=["jpg", "jpeg", "png", "webp", "gif"],
                timeout=30,
            )
            image_url = result.get("secure_url")
            uploaded_public_id = result.get("public_id")
            if not image_url or not uploaded_public_id:
                raise cloudinary.exceptions.Error("Cloudinary response did not include the uploaded image URL and public ID.")
            setattr(obj, self.url_field, image_url)
            if self.public_id_field:
                setattr(obj, self.public_id_field, uploaded_public_id)
        try:
            super().save_model(request, obj, form, change)
        except (IntegrityError, DatabaseError):
            if uploaded_public_id:
                try:
                    cloudinary.uploader.destroy(uploaded_public_id, resource_type="image", timeout=15)
                except Exception:
                    logger.exception("Could not clean up Cloudinary asset after database save failure.")
            raise

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        try:
            return super().changeform_view(request, object_id, form_url, extra_context)
        except IntegrityError:
            logger.exception("Admin save rejected by a database integrity constraint.")
            messages.error(
                request,
                "The record was not saved because it conflicts with a database constraint "
                "(for example, a duplicate slug/name or an invalid relationship). Review the fields and retry.",
            )
            return redirect(request.path)
        except DatabaseError:
            logger.exception("Admin save failed because of a database error.")
            messages.error(request, "The database could not save this record. Check backend logs and retry.")
            return redirect(request.path)
        except cloudinary.exceptions.Error:
            logger.exception("Cloudinary rejected or failed an admin image upload.")
            messages.error(
                request,
                "Cloudinary could not upload this image. Check Render's Cloudinary credentials and Cloudinary logs, then retry.",
            )
            return redirect(request.path)


@admin.register(Category)
class CategoryAdmin(CloudinaryUploadAdminMixin, admin.ModelAdmin):
    change_form_template = "api/admin/change_form_bottom_only.html"
    form = CategoryAdminForm
    upload_field = "image_upload"
    url_field = "image_url"
    upload_folder = "bala-fashion/categories"
    list_display = ("thumbnail", "name", "sort_order", "is_active", "image_status")
    list_display_links = ("name",)
    list_editable = ("sort_order", "is_active")
    list_per_page = 25
    save_on_top = False
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
    change_form_template = "api/admin/change_form_bottom_only.html"
    form = VendorAdminForm
    upload_field = "logo_upload"
    url_field = "logo_url"
    upload_folder = "bala-fashion/vendor-logos"
    list_display = ("thumbnail", "name", "status", "phone", "created_at")
    list_display_links = ("name",)
    list_editable = ("status",)
    list_per_page = 25
    save_on_top = False
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

    def save_model(self, request, obj, form, change):
        # Vendor ownership is a Supabase Auth UUID, not a Django staff-user ID.
        if not obj.owner_id:
            obj.owner_id = None
        super().save_model(request, obj, form, change)

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
    change_form_template = "api/admin/change_form_bottom_only.html"
    form = ProductAdminForm
    upload_field = "image_upload"
    url_field = "image_url"
    public_id_field = "image_public_id"
    upload_folder = "bala-fashion/products"
    list_display = ("thumbnail", "name", "price", "stock_quantity", "category", "vendor", "is_active", "image_status")
    list_display_links = ("name",)
    list_per_page = 25
    save_on_top = False
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
