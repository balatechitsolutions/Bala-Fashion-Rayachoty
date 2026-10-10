from unittest.mock import patch
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory
from . import views

class EndpointTests(SimpleTestCase):
    def setUp(self): self.factory=APIRequestFactory()
    def test_health_without_database_is_ok_but_not_configured(self):
        req=self.factory.get("/api/health/")
        with patch.object(views.os,"getenv",side_effect=lambda k,d=None:"" if k=="DATABASE_URL" else d):
            res=views.health(req)
        self.assertEqual(res.status_code,200)
        self.assertEqual(res.data["database"],"not_configured")
    def test_health_database_failure_is_503(self):
        req=self.factory.get("/api/health/")
        with patch.object(views.os,"getenv",return_value="postgresql://example"):
            with patch.object(views.connection,"cursor",side_effect=Exception("db down")):
                res=views.health(req)
        self.assertEqual(res.status_code,503)
    def test_orders_requires_bearer(self):
        res=views.orders(self.factory.get("/api/orders/"))
        self.assertEqual(res.status_code,401)
    def test_upload_signature_requires_auth(self):
        res=views.upload_signature(self.factory.post("/api/uploads/signature/",{},format="json"))
        self.assertEqual(res.status_code,401)
    def test_order_requires_address_and_items(self):
        req=self.factory.post("/api/orders/",{"items":[]},format="json",HTTP_AUTHORIZATION="Bearer test")
        with patch.object(views,"_user",return_value=({"id":"f2cb3c32-51d4-46aa-8ec2-785f18b7fd11"},None)):
            res=views.orders(req)
        self.assertEqual(res.status_code,400)


    def test_supabase_auth_user_directory_shows_setup_hint_without_secret(self):
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser
        from . import admin as admin_module
        request = RequestFactory().get("/admin/supabase-users/")
        request.user = AnonymousUser()
        with patch.dict("os.environ", {"SUPABASE_SERVICE_ROLE_KEY": "", "SUPABASE_URL": ""}, clear=False):
            response = admin_module.supabase_auth_users_view(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"SUPABASE_SERVICE_ROLE_KEY", response.content)
