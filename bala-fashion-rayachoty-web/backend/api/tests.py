from unittest.mock import MagicMock, patch
from types import SimpleNamespace
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
            with patch.object(views, "connection", SimpleNamespace(cursor=MagicMock(side_effect=Exception("db down")))):
                res=views.health(req)
        self.assertEqual(res.status_code,503)
    def test_orders_requires_bearer(self):
        res=views.orders(self.factory.get("/api/orders/"))
        self.assertEqual(res.status_code,401)
    def test_upload_signature_requires_auth(self):
        res=views.upload_signature(self.factory.post("/api/uploads/signature/",{},format="json"))
        self.assertEqual(res.status_code,401)
    def test_seller_dashboard_requires_bearer(self):
        res=views.seller_dashboard(self.factory.get("/api/seller/dashboard/"))
        self.assertEqual(res.status_code,401)
    def test_admin_role_is_authorized_for_admin_endpoints(self):
        req=self.factory.get("/api/seller/dashboard/",HTTP_AUTHORIZATION="Bearer test")
        user={"id":"2d0f5b2c-cf10-463e-9190-ab2561a84229"}
        profile={"id":user["id"],"full_name":"Admin","phone":"","role":"admin"}
        with patch.object(views,"_user",return_value=(user,None)), patch.object(views,"_profile",return_value=profile):
            resolved_user,resolved_profile,error=views._role_user(req,{"vendor","admin"})
        self.assertIsNone(error)
        self.assertEqual(resolved_profile["role"],"admin")

    def test_vendor_role_is_authorized_for_seller_endpoints(self):
        req=self.factory.get("/api/seller/dashboard/",HTTP_AUTHORIZATION="Bearer test")
        user={"id":"52c1edcc-bc32-44f7-b37b-f3a454617265"}
        profile={"id":user["id"],"full_name":"Seller","phone":"","role":"vendor"}
        with patch.object(views,"_user",return_value=(user,None)), patch.object(views,"_profile",return_value=profile):
            resolved_user,resolved_profile,error=views._role_user(req,{"vendor","admin"})
        self.assertIsNone(error)
        self.assertEqual(resolved_profile["role"],"vendor")

    def test_admin_role_is_authorized_for_admin_endpoints(self):
        req=self.factory.get("/api/seller/dashboard/",HTTP_AUTHORIZATION="Bearer test")
        user={"id":"2d0f5b2c-cf10-463e-9190-ab2561a84229"}
        profile={"id":user["id"],"full_name":"Admin","phone":"","role":"admin"}
        with patch.object(views,"_user",return_value=(user,None)), patch.object(views,"_profile",return_value=profile):
            resolved_user,resolved_profile,error=views._role_user(req,{"vendor","admin"})
        self.assertIsNone(error)
        self.assertEqual(resolved_profile["role"],"admin")

    def test_vendor_role_is_authorized_for_seller_endpoints(self):
        req=self.factory.get("/api/seller/dashboard/",HTTP_AUTHORIZATION="Bearer test")
        user={"id":"52c1edcc-bc32-44f7-b37b-f3a454617265"}
        profile={"id":user["id"],"full_name":"Seller","phone":"","role":"vendor"}
        with patch.object(views,"_user",return_value=(user,None)), patch.object(views,"_profile",return_value=profile):
            resolved_user,resolved_profile,error=views._role_user(req,{"vendor","admin"})
        self.assertIsNone(error)
        self.assertEqual(resolved_profile["role"],"vendor")

    def test_customer_cannot_access_seller_dashboard(self):
        req=self.factory.get("/api/seller/dashboard/",HTTP_AUTHORIZATION="Bearer test")
        user={"id":"f2cb3c32-51d4-46aa-8ec2-785f18b7fd11"}
        profile={"id":user["id"],"full_name":"Customer","phone":"","role":"customer"}
        with patch.object(views,"_user",return_value=(user,None)), patch.object(views,"_profile",return_value=profile):
            res=views.seller_dashboard(req)
        self.assertEqual(res.status_code,403)
    def test_customer_cannot_request_upload_signature(self):
        req=self.factory.post("/api/uploads/signature/",{},format="json",HTTP_AUTHORIZATION="Bearer test")
        user={"id":"f2cb3c32-51d4-46aa-8ec2-785f18b7fd11"}
        profile={"id":user["id"],"full_name":"Customer","phone":"","role":"customer"}
        with patch.object(views,"_user",return_value=(user,None)), patch.object(views,"_profile",return_value=profile):
            res=views.upload_signature(req)
        self.assertEqual(res.status_code,403)
    def test_admin_can_republish_hidden_product(self):
        from unittest.mock import MagicMock
        product_id = "f2cb3c32-51d4-46aa-8ec2-785f18b7fd11"
        req = self.factory.patch(
            "/api/products/manage/",
            {"id": product_id, "is_active": True},
            format="json",
            HTTP_AUTHORIZATION="Bearer test",
        )
        user = {"id": "2d0f5b2c-cf10-463e-9190-ab2561a84229"}
        profile = {"id": user["id"], "full_name": "Admin", "phone": "", "role": "admin"}
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [(product_id, "Hidden shirt"), (product_id, "Hidden shirt", True)]
        with patch.object(views, "_user", return_value=(user, None)), \
             patch.object(views, "_profile", return_value=profile), \
             patch.object(views, "connection", SimpleNamespace(cursor=MagicMock(return_value=cursor))):
            response = views.manage_product(req)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["is_active"])
        self.assertEqual(response.data["detail"], "Product published.")

    def test_customer_cannot_republish_product(self):
        product_id = "f2cb3c32-51d4-46aa-8ec2-785f18b7fd11"
        req = self.factory.patch(
            "/api/products/manage/",
            {"id": product_id, "is_active": True},
            format="json",
            HTTP_AUTHORIZATION="Bearer test",
        )
        user = {"id": product_id}
        profile = {"id": user["id"], "full_name": "Customer", "phone": "", "role": "customer"}
        with patch.object(views, "_user", return_value=(user, None)), \
             patch.object(views, "_profile", return_value=profile):
            response = views.manage_product(req)
        self.assertEqual(response.status_code, 403)

    def test_manage_orders_requires_bearer(self):
        response = views.manage_orders(self.factory.get("/api/orders/manage/"))
        self.assertEqual(response.status_code, 401)

    def test_customer_cannot_manage_orders(self):
        req = self.factory.get("/api/orders/manage/", HTTP_AUTHORIZATION="Bearer test")
        user = {"id": "f2cb3c32-51d4-46aa-8ec2-785f18b7fd11"}
        profile = {"id": user["id"], "full_name": "Customer", "phone": "", "role": "customer"}
        with patch.object(views, "_user", return_value=(user, None)), patch.object(views, "_profile", return_value=profile):
            response = views.manage_orders(req)
        self.assertEqual(response.status_code, 403)

    def test_order_requires_address_and_items(self):
        req=self.factory.post("/api/orders/",{"items":[]},format="json",HTTP_AUTHORIZATION="Bearer test")
        with patch.object(views,"_user",return_value=({"id":"f2cb3c32-51d4-46aa-8ec2-785f18b7fd11"},None)):
            res=views.orders(req)
        self.assertEqual(res.status_code,400)

    def test_django_admin_uuid_page_is_registered(self):
        from django.urls import resolve
        match = resolve('/admin/vendor-uuids/')
        self.assertEqual(match.url_name, 'admin-vendor-uuids')

    def test_delivered_cod_order_marks_payment_paid(self):
        from contextlib import nullcontext
        from datetime import datetime, timezone

        order_id = "a2e4b2d8-2b77-4b84-a420-0e30e2a7d6aa"
        req = self.factory.patch(
            "/api/orders/manage/",
            {"id": order_id, "status": "delivered"},
            format="json",
            HTTP_AUTHORIZATION="Bearer test",
        )
        user = {"id": "2d0f5b2c-cf10-463e-9190-ab2561a84229"}
        profile = {"id": user["id"], "full_name": "Admin", "phone": "", "role": "admin"}
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.side_effect = [
            (order_id, "out_for_delivery", "cod", "pending"),
            (order_id, "BFR-TEST123", "delivered", "paid", "1499.00", datetime.now(timezone.utc)),
        ]
        with patch.object(views, "_user", return_value=(user, None)):
            with patch.object(views, "_profile", return_value=profile):
                with patch.object(views, "connection", SimpleNamespace(cursor=MagicMock(return_value=cursor))):
                    with patch.object(views.transaction, "atomic", return_value=nullcontext()):
                        response = views.manage_orders(req)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "delivered")
        self.assertEqual(response.data["payment_status"], "paid")
        update_call = cursor.execute.call_args_list[-1]
        self.assertIn("payment_status=case", update_call.args[0].lower())
        self.assertEqual(update_call.args[1], ["delivered", "delivered", order_id])
