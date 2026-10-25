import logging
import os
import requests

from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.http import HttpResponse
from django.utils.html import escape
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction, connection
from django.utils import timezone
from django.utils.html import format_html
from django.utils.text import slugify
import cloudinary
import cloudinary.exceptions
import cloudinary.uploader

from .models import Category, CustomerAddress, DeliveryStaff, OrderRecord, Product, ProductImage, Vendor

logger = logging.getLogger(__name__)


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


class ProductImageInlineForm(CloudinaryUploadFormMixin, forms.ModelForm):
    image_upload = forms.FileField(
        required=False,
        label="Upload gallery image to Cloudinary",
        help_text="JPG, PNG, WebP or GIF. Maximum 8 MB per image.",
    )

    class Meta:
        model = ProductImage
        fields = ("alt_text", "sort_order")

    def clean_image_upload(self):
        image = self.cleaned_data.get("image_upload")
        self._validate_upload(image)
        if self.instance._state.adding and not image:
            raise ValidationError("Choose an image file for each new gallery row.")
        return image


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    form = ProductImageInlineForm
    extra = 0
    max_num = 8
    validate_max = True
    fields = ("image_upload", "preview", "alt_text", "sort_order")
    readonly_fields = ("preview",)
    ordering = ("sort_order", "created_at")

    @admin.display(description="Current Cloudinary image")
    def preview(self, obj):
        if obj and obj.image_url:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener"><img src="{}" alt="Product gallery image" '
                'style="width:76px;height:76px;object-fit:contain;border-radius:8px;background:#f3f4f6;padding:4px;"></a>',
                obj.image_url, obj.image_url,
            )
        return "Uploaded image preview appears after saving"


class VendorAdminForm(CloudinaryUploadFormMixin, forms.ModelForm):
    logo_upload = forms.FileField(
        required=False,
        label="Upload vendor logo",
        help_text="Choose a logo to upload to Cloudinary. Maximum 8 MB.",
    )

    class Meta:
        model = Vendor
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "owner_id" in self.fields:
            self.fields["owner_id"].label = "User UUID (Supabase Auth)"
            self.fields["owner_id"].help_text = "Paste the existing Supabase Auth user UUID. Do not use a Django admin user ID."

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


class CloudinaryUploadFailure(Exception):
    """A safe-to-display failure while uploading an admin image to Cloudinary."""


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
            try:
                result = cloudinary.uploader.upload(
                    uploaded,
                    folder=self.upload_folder,
                    resource_type="image",
                    allowed_formats=["jpg", "jpeg", "png", "webp", "gif"],
                )
            except Exception as exc:
                # Cloudinary can fail with SDK errors, HTTP errors, timeouts,
                # DNS failures, or connection errors. Handle all upload failures
                # through Django Admin messaging instead of returning an unhandled 500.
                logger.error(
                    "Cloudinary image upload failed (%s): %s",
                    type(exc).__name__,
                    str(exc)[:500],
                    exc_info=True,
                )
                raise CloudinaryUploadFailure(
                    "Image upload failed. Check the Cloudinary credentials and the latest "
                    "Render application logs for the exact cause. The record was not saved."
                ) from exc
            image_url = result.get("secure_url")
            uploaded_public_id = result.get("public_id")
            if not image_url or not uploaded_public_id:
                raise CloudinaryUploadFailure(
                    "Cloudinary response did not include the uploaded image URL and public ID."
                )
            setattr(obj, self.url_field, image_url)
            if self.public_id_field:
                setattr(obj, self.public_id_field, uploaded_public_id)
        try:
            super().save_model(request, obj, form, change)
        except (IntegrityError, DatabaseError):
            if uploaded_public_id:
                try:
                    cloudinary.uploader.destroy(uploaded_public_id, resource_type="image")
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
        except CloudinaryUploadFailure:
            logger.exception("Cloudinary rejected or failed an admin image upload.")
            messages.error(
                request,
                "Cloudinary could not upload this image. Check Render's Cloudinary credentials and Cloudinary logs, then retry.",
            )
            return redirect(request.path)


@admin.register(Category)
class CategoryAdmin(CloudinaryUploadAdminMixin, admin.ModelAdmin):
    form = CategoryAdminForm
    upload_field = "image_upload"
    url_field = "image_url"
    upload_folder = "Bala_fashon_Rayachoty"
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
        return format_html('<img src="{}" alt="Category image" style="width:56px;height:56px;max-width:56px;max-height:56px;object-fit:contain;border-radius:8px;background:#f3f4f6;padding:4px;box-sizing:border-box;">', obj.image_url) if obj.image_url else "—"

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
    upload_folder = "Bala_fashon_Rayachoty"
    list_display = ("thumbnail", "name", "owner_uuid", "status", "phone", "created_at")
    list_display_links = ("name",)
    list_editable = ("status",)
    list_per_page = 25
    save_on_top = False
    actions = ("approve", "suspend")
    list_filter = ("status", "created_at")
    search_fields = ("name", "slug", "phone", "address", "owner_id")
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

    @admin.display(description="User UUID")
    def owner_uuid(self, obj):
        return str(obj.owner_id) if obj.owner_id else "Not linked"

    @admin.display(description="Logo")
    def thumbnail(self, obj):
        return format_html('<img src="{}" alt="Vendor logo" style="width:56px;height:56px;max-width:56px;max-height:56px;object-fit:contain;border-radius:8px;background:#f3f4f6;padding:4px;box-sizing:border-box;">', obj.logo_url) if obj.logo_url else "—"

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
    upload_folder = "Bala_fashon_Rayachoty"
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
    inlines = (ProductImageInline,)
    fieldsets = (
        ("Product details", {"fields": ("name", "slug", "vendor", "category", "sku", "description", "additional_description")}),
        ("Pricing & inventory", {"fields": ("price", "compare_at_price", "stock_quantity", "sizes_text", "colors_text")}),
        ("Main product image", {"fields": ("image_upload", "image_url", "image_public_id")}),
        ("Store visibility", {"fields": ("is_active",)}),
        ("Record information", {"fields": ("created_at", "updated_at")}),
    )

    def save_formset(self, request, form, formset, change):
        # Upload selected files server-side; Django Admin never sends files directly from the browser to Cloudinary.
        if formset.model is ProductImage:
            for inline_form in formset.forms:
                if not hasattr(inline_form, "cleaned_data") or not inline_form.cleaned_data:
                    continue
                if inline_form.cleaned_data.get("DELETE"):
                    continue
                uploaded = inline_form.cleaned_data.get("image_upload")
                if not uploaded:
                    continue
                cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
                api_key = os.getenv("CLOUDINARY_API_KEY", "").strip()
                api_secret = os.getenv("CLOUDINARY_API_SECRET", "").strip()
                if not all((cloud_name, api_key, api_secret)):
                    raise CloudinaryUploadFailure("Cloudinary credentials are not configured on the backend.")
                cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)
                try:
                    result = cloudinary.uploader.upload(
                        uploaded,
                        folder="Bala_fashon_Rayachoty/products/gallery",
                        resource_type="image",
                        allowed_formats=["jpg", "jpeg", "png", "webp", "gif"],
                    )
                except Exception as exc:
                    logger.error("Cloudinary gallery upload failed (%s): %s", type(exc).__name__, str(exc)[:500], exc_info=True)
                    raise CloudinaryUploadFailure(
                        "Gallery upload failed. Check Render Cloudinary credentials/logs; gallery changes were not saved."
                    ) from exc
                if not result.get("secure_url") or not result.get("public_id"):
                    raise CloudinaryUploadFailure("Cloudinary did not return a secure image URL and public ID.")
                inline_form.instance.image_url = result["secure_url"]
                inline_form.instance.image_public_id = result["public_id"]
                inline_form.instance.product = form.instance
            formset.save()
            return
        super().save_formset(request, form, formset, change)

    @admin.display(description="Preview")
    def thumbnail(self, obj):
        return format_html('<img src="{}" alt="Product image" style="width:56px;height:56px;max-width:56px;max-height:56px;object-fit:contain;border-radius:8px;background:#f3f4f6;padding:4px;box-sizing:border-box;">', obj.image_url) if obj.image_url else "—"

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



class DeliveryStaffAdminForm(forms.ModelForm):
    class Meta:
        model = DeliveryStaff
        fields = ("id", "full_name", "phone")

    def clean_id(self):
        user_id = self.cleaned_data["id"]
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM auth.users WHERE id=%s LIMIT 1", [str(user_id)])
                if not cursor.fetchone():
                    raise ValidationError("This UUID does not exist in Supabase Authentication → Users.")
                cursor.execute("SELECT role FROM public.profiles WHERE id=%s LIMIT 1", [str(user_id)])
                profile = cursor.fetchone()
                if profile and profile[0] == "admin":
                    raise ValidationError("An administrator account cannot be converted to delivery staff.")
        except ValidationError:
            raise
        except DatabaseError as exc:
            logger.exception("Could not validate Supabase user before adding delivery staff.")
            raise ValidationError("Supabase user could not be verified. Check the database connection and try again.") from exc
        return user_id


@admin.register(DeliveryStaff)
class DeliveryStaffAdmin(admin.ModelAdmin):
    """Manage delivery staff profiles in the existing Supabase-owned profiles table."""

    form = DeliveryStaffAdminForm
    list_display = ("full_name", "id", "phone", "updated_at")
    list_display_links = None
    list_filter = ("role",)
    search_fields = ("full_name", "phone", "id")
    ordering = ("full_name", "id")
    list_per_page = 50
    readonly_fields = ("role", "updated_at")
    fields = ("id", "full_name", "phone", "role", "updated_at")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(role="delivery_boy")

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return ((None, {"fields": ("id", "full_name", "phone")}),)
        return super().get_fieldsets(request, obj)

    def save_model(self, request, obj, form, change):
        # Promote an existing Supabase Auth user in the existing profiles table.
        # Updating avoids duplicate-key errors when the user already has a profile.
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE public.profiles
                    SET full_name=%s, phone=%s, role='delivery_boy', updated_at=NOW()
                    WHERE id=%s
                    """,
                    [obj.full_name or "", obj.phone or "", str(obj.id)],
                )
                if cursor.rowcount == 0:
                    cursor.execute(
                        """
                        INSERT INTO public.profiles (id, full_name, phone, role, updated_at)
                        VALUES (%s, %s, %s, 'delivery_boy', NOW())
                        """,
                        [str(obj.id), obj.full_name or "", obj.phone or ""],
                    )
        messages.success(request, "Delivery staff account added successfully.")

    def has_add_permission(self, request):
        # Superusers may add delivery staff by linking an existing Supabase Auth UUID.
        return request.user.is_active and request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser and request.method in ("GET", "HEAD")

    def has_delete_permission(self, request, obj=None):
        return False


def user_uuids_admin_view(request):
    """Fetch every Supabase Auth UUID through the Supabase Admin API."""
    from django.core.exceptions import PermissionDenied
    from django.utils.html import escape

    if not request.user.is_active or not request.user.is_superuser:
        raise PermissionDenied

    supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_url or not service_key:
        message = (
            "Supabase UUID fetch is not configured. Add SUPABASE_URL and "
            "SUPABASE_SERVICE_ROLE_KEY to the Render backend environment."
        )
        return HttpResponse(
            "<!doctype html><html><head><meta charset='utf-8'><title>User UUIDs</title></head>"
            "<body style='font:15px system-ui;margin:28px'><h1>All Supabase User UUIDs</h1><p>"
            + escape(message) + "</p><p><a href='/admin/'>Back to admin</a></p></body></html>",
            status=503,
        )

    users = []
    page = 1
    per_page = 1000
    try:
        while True:
            response = requests.get(
                f"{supabase_url}/auth/v1/admin/users",
                headers={
                    "apikey": service_key,
                    "Authorization": f"Bearer {service_key}",
                },
                params={"page": page, "per_page": per_page},
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("users", []) if isinstance(payload, dict) else []
            users.extend(batch)
            if len(batch) < per_page:
                break
            page += 1
            if page > 1000:
                raise RuntimeError("Supabase returned an unexpectedly large number of pages.")
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        logger.exception("Supabase Auth UUID fetch failed.")
        detail = (
            "Supabase could not return the user directory. Check the Render "
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY values and the latest "
            "Render logs. The service-role key must be kept secret."
        )
        return HttpResponse(
            "<!doctype html><html><head><meta charset='utf-8'><title>User UUIDs</title></head>"
            "<body style='font:15px system-ui;margin:28px'><h1>All Supabase User UUIDs</h1><p>"
            + escape(detail) + "</p><p><a href='/admin/'>Back to admin</a></p></body></html>",
            status=503,
        )

    body_rows = []
    for user in users:
        user_id = str(user.get("id") or "")
        if not user_id:
            continue
        email = str(user.get("email") or "")
        metadata = user.get("user_metadata") or {}
        name = str(metadata.get("full_name") or metadata.get("name") or "")
        role = str(metadata.get("role") or "customer")
        body_rows.append(
            "<tr data-search=\"" + escape(" ".join((user_id, email, name, role)).lower()) + "\">"
            "<td><code class='user-uuid'>" + escape(user_id) + "</code></td><td>" + escape(email) +
            "</td><td>" + escape(name) + "</td><td>" + escape(role) +
            "</td><td><button type='button' class='copy-one' data-uuid='" + escape(user_id) +
            "' aria-label='Copy UUID for " + escape(email or user_id) + "'>Copy UUID</button></td></tr>"
        )

    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'><title>All User UUIDs</title>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<style>"
        ":root{color-scheme:light}*{box-sizing:border-box}body{font:15px/1.5 system-ui,-apple-system,sans-serif;"
        "margin:0;background:#f2f5fa;color:#172033}.page{max-width:1200px;margin:auto;padding:clamp(14px,3vw,30px)}"
        ".top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:18px}"
        "h1{font-size:clamp(23px,4vw,32px);margin:0;color:#102b50}.muted{color:#526078}"
        ".panel{background:#fff;border:1px solid #cbd5e1;border-radius:14px;padding:clamp(14px,2.5vw,22px);"
        "box-shadow:0 3px 12px #0f172a0b}.tools{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;"
        "align-items:center;margin:18px 0}.search{width:100%;min-width:0;padding:12px 14px;border:1px solid #9aa9bd;"
        "border-radius:8px;font:inherit;color:#172033;background:#fff}.btn{border:0;border-radius:8px;padding:11px 15px;"
        "background:#123a72;color:#fff;font:700 14px system-ui;cursor:pointer;text-decoration:none;display:inline-flex;"
        "align-items:center;justify-content:center;min-height:42px}.btn:focus-visible,.search:focus-visible{outline:3px solid #91bfff;"
        "outline-offset:2px}.count{font-weight:700;color:#102b50;margin:0 0 12px}.table-wrap{overflow-x:auto;"
        "border:1px solid #d8e0eb;border-radius:10px}table{border-collapse:collapse;width:100%;min-width:680px;background:#fff}"
        "th,td{padding:12px 13px;border-bottom:1px solid #e1e7f0;text-align:left;vertical-align:middle}"
        "th{background:#e9eff8;color:#102b50;font-size:13px;position:sticky;top:0}tbody tr:nth-child(even){background:#f8faff}"
        "code{overflow-wrap:anywhere;word-break:break-word;font-size:12px}.copy-one{border:1px solid #123a72;"
        "background:#fff;color:#123a72;border-radius:7px;padding:8px 11px;font-weight:800;cursor:pointer;white-space:nowrap}"
        ".copy-one:hover{background:#e9eff8}.empty{display:none;padding:18px;text-align:center;color:#526078}"
        "@media(max-width:640px){.page{padding:12px}.tools{grid-template-columns:1fr}.top .btn{width:100%}"
        ".panel{padding:12px}th,td{padding:10px}}"
        "</style></head><body><main class='page'><div class='top'><div><h1>Supabase User UUIDs</h1>"
        "<p class='muted'>Search the fetched Supabase Auth directory, then copy only the UUID you need.</p></div>"
        "<a class='btn' href='/admin/'>Back to admin</a></div><section class='panel'>"
        "<p class='count'>Fetched " + str(len(body_rows)) + " accounts from Supabase Auth.</p>"
        "<div class='tools'><input id='user-search' class='search' type='search' placeholder='Search email, name, role or UUID…' "
        "aria-label='Search fetched users' autocomplete='off'><span id='shown-count' class='muted'></span></div>"
        "<div class='table-wrap'><table><thead><tr><th>User UUID</th><th>Email</th><th>Name</th><th>Role metadata</th><th>Action</th>"
        "</tr></thead><tbody id='user-rows'>" + "".join(body_rows) + "</tbody></table>"
        "<div id='empty-state' class='empty'>No users match your search.</div></div>"
        "<p id='copy-status' class='muted' role='status' aria-live='polite'></p></section></main>"
        "<script>(function(){const input=document.getElementById('user-search');"
        "const rows=Array.from(document.querySelectorAll('#user-rows tr'));const count=document.getElementById('shown-count');"
        "const empty=document.getElementById('empty-state');const status=document.getElementById('copy-status');"
        "function filterRows(){const q=input.value.trim().toLowerCase();let shown=0;rows.forEach(row=>{"
        "const match=(row.dataset.search||'').includes(q);row.hidden=!match;if(match)shown++;});"
        "count.textContent=shown+' of '+rows.length+' users';empty.style.display=shown?'none':'block';}"
        "input.addEventListener('input',filterRows);filterRows();"
        "async function copyText(value){if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(value);return;}"
        "const field=document.createElement('textarea');field.value=value;field.style.position='fixed';field.style.opacity='0';"
        "document.body.appendChild(field);field.select();const ok=document.execCommand('copy');field.remove();"
        "if(!ok)throw new Error('Copy failed');}"
        "document.querySelectorAll('.copy-one').forEach(button=>button.addEventListener('click',async()=>{"
        "const value=button.dataset.uuid;try{await copyText(value);button.textContent='Copied ✓';status.textContent='UUID copied: '+value;"
        "setTimeout(()=>{button.textContent='Copy UUID';},1500);}catch(e){status.textContent='Copy was blocked. Select the UUID text and copy it manually.';}}));"
        "})();</script></body></html>"
    )
    return HttpResponse(html)


@admin.register(CustomerAddress)
class CustomerAddressAdmin(admin.ModelAdmin):
    """Manage saved customer addresses directly in Django admin."""
    list_display = ("recipient_name", "phone", "user_id", "city", "postal_code", "is_default", "updated_at")
    list_filter = ("is_default", "city", "state")
    search_fields = ("recipient_name", "phone", "user_id", "line1", "line2", "landmark", "postal_code")
    readonly_fields = ("id", "created_at", "updated_at")
    list_per_page = 50
    ordering = ("-updated_at",)
    fieldsets = (
        ("Customer", {"fields": ("user_id", "recipient_name", "phone")}),
        ("Delivery address", {"fields": ("line1", "line2", "landmark", "city", "state", "postal_code", "latitude", "longitude", "notes")}),
        ("Default address", {"fields": ("is_default",)}),
        ("Record information", {"fields": ("id", "created_at", "updated_at")}),
    )

    def save_model(self, request, obj, form, change):
        with transaction.atomic():
            if obj.is_default:
                CustomerAddress.objects.filter(user_id=obj.user_id).exclude(pk=obj.pk).update(is_default=False)
            obj.updated_at = timezone.now()
            super().save_model(request, obj, form, change)


@admin.register(OrderRecord)
class OrderRecordAdmin(admin.ModelAdmin):
    """Search orders and repair their saved address snapshot without altering payment/items."""
    list_display = ("order_number", "customer_id", "status", "payment_status", "total", "created_at", "address_state")
    list_filter = ("status", "payment_status", "payment_method")
    search_fields = ("order_number", "customer_id", "vendor_id")
    readonly_fields = ("id", "order_number", "customer_id", "vendor_id", "status", "payment_method", "payment_status", "subtotal", "delivery_fee", "total", "notes", "created_at", "address_state")
    fields = ("id", "order_number", "customer_id", "vendor_id", "status", "payment_method", "payment_status", "subtotal", "delivery_fee", "total", "address_state", "address_snapshot", "notes", "created_at")
    list_per_page = 50

    @admin.display(description="Delivery address")
    def address_state(self, obj):
        snapshot = obj.address_snapshot if isinstance(obj.address_snapshot, dict) else {}
        return "Saved" if snapshot.get("line1") and snapshot.get("recipient_name") else "Missing / incomplete"

    def save_model(self, request, obj, form, change):
        # Only editable field is address_snapshot; order totals, items and payment stay untouched.
        super().save_model(request, obj, form, change)
