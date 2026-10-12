# Generated for the native DeliveryStaff admin model.
import django.db.models.deletion
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="DeliveryStaff",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("supabase_user_id", models.UUIDField(
                    unique=True,
                    help_text="UUID of the existing user in Supabase Auth. This does not create a Supabase login.",
                )),
                ("full_name", models.CharField(max_length=120)),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                ("phone", models.CharField(blank=True, default="", max_length=30)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Delivery staff",
                "verbose_name_plural": "Delivery staff",
                "db_table": "delivery_staff",
                "ordering": ("full_name", "id"),
            },
        ),
    ]
