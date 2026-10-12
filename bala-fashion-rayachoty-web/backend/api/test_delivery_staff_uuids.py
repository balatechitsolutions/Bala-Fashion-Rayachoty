from unittest.mock import MagicMock, patch
from types import SimpleNamespace

from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase, override_settings

from config import urls


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
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

    @patch("config.urls.connection")
    def test_superuser_can_view_delivery_staff_uuids_without_django_model(self, connection_mock):
        cursor = MagicMock()
        connection_mock.cursor.return_value.__enter__.return_value = cursor
        def set_result_shape(sql, params=None):
            if "FROM public.profiles p" in sql:
                cursor.description = [("id",), ("full_name",), ("phone",), ("updated_at",), ("email",)]
            else:
                cursor.description = [("id",), ("email",), ("full_name",), ("created_at",), ("role",)]
        cursor.execute.side_effect = set_result_shape
        cursor.fetchall.side_effect = [
            [("3db4b2df-77f9-4e25-93a6-32a50f8f70c1", "Delivery Worker", "9876543210", None, "delivery@example.com")],
            [("3db4b2df-77f9-4e25-93a6-32a50f8f70c1", "delivery@example.com", "Delivery Worker", None, "delivery_boy")],
        ]

        response = urls.delivery_staff_uuids(self.admin_request())

        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Delivery Staff UUIDs", body)
        self.assertIn("3db4b2df-77f9-4e25-93a6-32a50f8f70c1", body)
        self.assertIn("delivery@example.com", body)
        self.assertEqual(cursor.execute.call_count, 2)
        self.assertIn("public.profiles", cursor.execute.call_args_list[0].args[0])
        self.assertEqual(cursor.execute.call_args_list[0].args[1], ["delivery_boy"])
        self.assertIn("auth.users", cursor.execute.call_args_list[1].args[0])

    def test_non_superuser_staff_cannot_view_delivery_staff_uuids(self):
        with self.assertRaises(PermissionDenied):
            urls.delivery_staff_uuids(self.admin_request(is_superuser=False))
