from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase

from config import urls


class DeliveryStaffUUIDAdminTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def admin_request(self, is_superuser=True):
        request = self.factory.get("/admin/delivery-staff-uuids/")
        SessionMiddleware(lambda req: None).process_request(request)
        request.user = SimpleNamespace(
            is_active=True,
            is_staff=True,
            is_superuser=is_superuser,
        )
        return request

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

        response = urls.delivery_staff_uuids(self.admin_request())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delivery Staff UUIDs")
        self.assertContains(response, "3db4b2df-77f9-4e25-93a6-32a50f8f70c1")
        cursor.execute.assert_called_once()
        self.assertIn("public.profiles", cursor.execute.call_args.args[0])
        self.assertEqual(cursor.execute.call_args.args[1], ["delivery_boy"])

    def test_non_superuser_staff_cannot_view_delivery_staff_uuids(self):
        with self.assertRaises(PermissionDenied):
            urls.delivery_staff_uuids(self.admin_request(is_superuser=False))
