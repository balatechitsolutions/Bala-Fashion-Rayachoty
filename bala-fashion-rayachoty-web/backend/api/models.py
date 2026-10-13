import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    image_url = models.TextField(blank=True, default="")
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "categories"
        ordering = ("sort_order", "name")

    def __str__(self):
        return self.name


class Vendor(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("suspended", "Suspended"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner_id = models.UUIDField(null=True, blank=True)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")
    logo_url = models.TextField(blank=True, default="")
    phone = models.CharField(max_length=100, blank=True, default="")
    address = models.TextField(blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "vendors"
        ordering = ("name",)

    def __str__(self):
        return self.name


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vendor = models.ForeignKey(Vendor, db_column="vendor_id", on_delete=models.PROTECT, related_name="products")
    category = models.ForeignKey(Category, db_column="category_id", on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    name = models.CharField(max_length=180)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True, default="")
    price = models.DecimalField(max_digits=12, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sku = models.CharField(max_length=255, blank=True, default="")
    image_url = models.TextField(blank=True, default="")
    image_public_id = models.CharField(max_length=255, blank=True, default="")
    sizes = ArrayField(models.CharField(max_length=30), default=list, blank=True)
    colors = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    stock_quantity = models.IntegerField(default=0)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "products"
        ordering = ("-created_at",)

    def __str__(self):
        return self.name



class DeliveryStaff(models.Model):
    """
    Read-only Django mapping for delivery staff profiles stored by Supabase Auth.

    This model intentionally does not manage the shared public.profiles table;
    Django must never create or alter the Supabase-owned schema.
    """
    id = models.UUIDField(primary_key=True)
    full_name = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=100, null=True, blank=True)
    role = models.CharField(max_length=32)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "profiles"
        ordering = ("full_name", "id")
        verbose_name = "Delivery staff"
        verbose_name_plural = "Delivery staff"

    def __str__(self):
        return self.full_name or str(self.id)


class CustomerAddress(models.Model):
    """Django mapping of Supabase public.customer_addresses; schema is managed by Supabase."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.UUIDField()
    recipient_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)
    line1 = models.CharField(max_length=200)
    line2 = models.CharField(max_length=200, blank=True, default="")
    landmark = models.CharField(max_length=160, blank=True, default="")
    city = models.CharField(max_length=100, default="Rayachoty")
    state = models.CharField(max_length=100, default="Andhra Pradesh")
    postal_code = models.CharField(max_length=12, blank=True, default="")
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "customer_addresses"
        ordering = ("-updated_at",)
        verbose_name = "Customer delivery address"
        verbose_name_plural = "Customer delivery addresses"

    def __str__(self):
        return f"{self.recipient_name} — {self.city} ({self.user_id})"


class OrderRecord(models.Model):
    """Django admin mapping for order support; actual table remains Supabase-managed."""
    id = models.UUIDField(primary_key=True)
    order_number = models.CharField(max_length=64)
    customer_id = models.UUIDField()
    vendor_id = models.UUIDField()
    status = models.CharField(max_length=40)
    payment_method = models.CharField(max_length=30)
    payment_status = models.CharField(max_length=30)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    address_snapshot = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "orders"
        ordering = ("-created_at",)
        verbose_name = "Order address"
        verbose_name_plural = "Order addresses"

    def __str__(self):
        return self.order_number
