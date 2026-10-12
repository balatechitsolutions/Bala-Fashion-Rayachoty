import uuid

from django.contrib.postgres.fields import ArrayField
from django.db import models


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
    """Django-managed directory record linked to an existing Supabase Auth user."""

    id = models.BigAutoField(primary_key=True)
    supabase_user_id = models.UUIDField(
        unique=True,
        help_text="UUID of the existing user in Supabase Auth. This does not create a Supabase login.",
    )
    full_name = models.CharField(max_length=120)
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=30, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "delivery_staff"
        ordering = ("full_name", "id")
        verbose_name = "Delivery staff"
        verbose_name_plural = "Delivery staff"

    def __str__(self):
        return f"{self.full_name} ({self.supabase_user_id})"
