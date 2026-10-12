from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase


class DeliveryStaffUUIDAdminTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_superuser(
            username="uuid-admin", email="uuid-admin@example.com", password="test-password-123"
        )
        self.staff_user = user_model.objects.create_user(
            username="ordinary-staff", email="ordinary@example.com",
            password="test-password-123", is_staff=True, is_superuser=False
        )

    @patch("config.urls.connection.cursor")
    def test_superuser_can_view_delivery_staff_uuids_without_django_model(self, cursor_factory):
        cursor = MagicMock()
        cursor_factory.return_value.__enter__.return_value = cursor
        cursor.description = [
            ("id",), ("full_name",), ("phone",), ("updated_at",)
        ]
        cursor.fetchall.return_value = [
            ("3db4b2df-77f9-4e25-93a6-32a50f8f70c1", "Delivery Worker", "9876543210", None)
        ]

        self.client.force_login(self.admin_user)
        response = self.client.get("/admin/delivery-staff-uuids/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delivery Staff UUIDs")
        self.assertContains(response, "3db4b2df-77f9-4e25-93a6-32a50f8f70c1")
        cursor.execute.assert_called_once()
        self.assertIn("public.profiles", cursor.execute.call_args.args[0])
        self.assertIn("delivery_boy", cursor.execute.call_args.args[1])
        
    def test_non_superuser_staff_cannot_view_delivery_staff_uuids(self):
        self.client.force_login(self.staff_user)
        response = self.client.get("/admin/delivery-staff-uuids/")
        self.assertEqual(response.status_code, 403)
