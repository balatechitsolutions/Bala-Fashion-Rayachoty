import logging
import os

from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
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
        if not self.instance.pk and not image:
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



@admin.register(DeliveryStaff)
class DeliveryStaffAdmin(admin.ModelAdmin):
    """Read-only admin view of profiles authorized for delivery work."""

    list_display = ("full_name", "id", "phone", "updated_at")
    list_display_links = None
    list_filter = ("role",)
    search_fields = ("full_name", "phone", "id")
    ordering = ("full_name", "id")
    list_per_page = 50
    readonly_fields = ("id", "full_name", "phone", "role", "updated_at")
    fields = ("id", "full_name", "phone", "role", "updated_at")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(role="delivery_boy")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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
