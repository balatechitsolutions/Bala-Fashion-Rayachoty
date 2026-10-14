from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from decimal import Decimal
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory
from . import views

class EndpointTests(SimpleTestCase):
    def setUp(self): self.factory=APIRequestFactory()
    def test_delivery_fee_rounds_up_to_next_500_metre_block(self):
        self.assertEqual(views.delivery_fee_for_distance(0), Decimal("0.00"))
        self.assertEqual(views.delivery_fee_for_distance(1), Decimal("5.00"))
        self.assertEqual(views.delivery_fee_for_distance(500), Decimal("5.00"))
        self.assertEqual(views.delivery_fee_for_distance(501), Decimal("10.00"))
        self.assertEqual(views.delivery_fee_for_distance(1000), Decimal("10.00"))
        self.assertEqual(views.delivery_fee_for_distance(5000), Decimal("50.00"))

    def test_delivery_fee_rejects_negative_or_non_numeric_distance(self):
        for distance in (-1, "not-a-distance"):
            with self.subTest(distance=distance), self.assertRaises(ValueError):
                views.delivery_fee_for_distance(distance)

    def test_coordinates_are_validated(self):
        self.assertEqual(views._coordinate("14.05", "latitude"), 14.05)
        for value in ("bad", "91", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                views._coordinate(value, "latitude")

    @patch.object(views.requests, "get")
    def test_road_distance_uses_osrm_route_distance(self, get):
        response = MagicMock()
        response.json.return_value = {"code": "Ok", "routes": [{"distance": 1250.5}]}
        get.return_value = response
        distance = views.road_distance_meters(14.05, 78.75, 14.06, 78.76)
        self.assertEqual(distance, 1250.5)
        self.assertIn("/route/v1/driving/78.75,14.05;78.76,14.06", get.call_args.args[0])

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
    def test_order_address_resolves_default_from_database(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = (
            "a1b2c3d4-1111-4222-8333-123456789abc", "Customer", "9876543210",
            "12 Main Road", "", "Near school", "Rayachoty", "Andhra Pradesh",
            "516269", 14.05, 78.75, "",
        )
        resolved = views._resolve_order_address(cursor, "customer-uuid")
        self.assertEqual(resolved["recipient_name"], "Customer")
        self.assertEqual(resolved["line1"], "12 Main Road")
        self.assertEqual(resolved["id"], "a1b2c3d4-1111-4222-8333-123456789abc")
        self.assertIn("is_default=true", cursor.execute.call_args.args[0])

    def test_order_address_rejects_address_not_owned_by_customer(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        with self.assertRaisesRegex(ValueError, "not found in your account"):
            views._resolve_order_address(cursor, "customer-uuid", "a1b2c3d4-1111-4222-8333-123456789abc")

    def test_order_address_requires_default_when_no_address_id_is_sent(self):
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        with self.assertRaisesRegex(ValueError, "No default delivery address"):
            views._resolve_order_address(cursor, "customer-uuid")

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

    @patch.object(views, "_user", return_value=({"id": "f2cb3c32-51d4-46aa-8ec2-785f18b7fd11"}, None))
    @patch.object(views, "road_distance_meters", return_value=1250.5)
    def test_delivery_quote_uses_road_distance_and_fee(self, road_distance, auth):
        vendor_id = "a2e4b2d8-2b77-4b84-a420-0e30e2a7d6aa"
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = ("Rayachoty Store", 14.05, 78.75)
        req = self.factory.post(
            "/api/delivery/quote/",
            {"vendor_id": vendor_id, "latitude": 14.06, "longitude": 78.76},
            format="json",
            HTTP_AUTHORIZATION="Bearer test",
        )
        with patch.object(views, "connection", SimpleNamespace(cursor=MagicMock(return_value=cursor))):
            response = views.delivery_quote(req)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["delivery_fee"], "15.00")
        self.assertEqual(response.data["distance_meters"], 1250)
        road_distance.assert_called_once()

    @patch.object(views, "_user", return_value=({"id": "f2cb3c32-51d4-46aa-8ec2-785f18b7fd11"}, None))
    @patch.object(views, "road_distance_meters", return_value=5200)
    def test_delivery_quote_rejects_routes_over_five_kilometres(self, road_distance, auth):
        vendor_id = "a2e4b2d8-2b77-4b84-a420-0e30e2a7d6aa"
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = ("Rayachoty Store", 14.05, 78.75)
        req = self.factory.post(
            "/api/delivery/quote/",
            {"vendor_id": vendor_id, "latitude": 14.06, "longitude": 78.76},
            format="json",
            HTTP_AUTHORIZATION="Bearer test",
        )
        with patch.object(views, "connection", SimpleNamespace(cursor=MagicMock(return_value=cursor))):
            response = views.delivery_quote(req)
        self.assertEqual(response.status_code, 400)
        self.assertIn("5 km", response.data["detail"])

    def test_order_requires_address_and_items(self):
        req=self.factory.post("/api/orders/",{"items":[]},format="json",HTTP_AUTHORIZATION="Bearer test")
        with patch.object(views,"_user",return_value=({"id":"f2cb3c32-51d4-46aa-8ec2-785f18b7fd11"},None)):
            res=views.orders(req)
        self.assertEqual(res.status_code,400)

    def test_standard_django_admin_dashboard_is_registered(self):
        from django.urls import resolve
        match = resolve('/admin/')
        self.assertEqual(match.url_name, 'index')
        custom_page = resolve('/admin/vendor-uuids/')
        self.assertNotEqual(custom_page.url_name, 'admin-vendor-uuids')

    def test_admin_cannot_mark_delivered_without_delivery_otp(self):
        from contextlib import nullcontext

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
        cursor.fetchone.return_value = (
            order_id, "out_for_delivery", "cod", "pending",
            "f2cb3c32-51d4-46aa-8ec2-785f18b7fd11", "BFR-TEST123",
        )
        with patch.object(views, "_user", return_value=(user, None)):
            with patch.object(views, "_profile", return_value=profile):
                with patch.object(views, "connection", SimpleNamespace(cursor=MagicMock(return_value=cursor))):
                    with patch.object(views.transaction, "atomic", return_value=nullcontext()):
                        response = views.manage_orders(req)

        # Admins are forbidden from changing order status through this endpoint;
        # delivery completion must go through the assigned delivery person's OTP flow.
        self.assertEqual(response.status_code, 403)
        update_calls = [call for call in cursor.execute.call_args_list if "update public.orders" in call.args[0].lower()]
        self.assertFalse(update_calls)


    def test_customer_cannot_access_delivery_staff_orders(self):
        from . import delivery
        req = self.factory.get("/api/delivery/orders/", HTTP_AUTHORIZATION="Bearer test")
        user = {"id": "f2cb3c32-51d4-46aa-8ec2-785f18b7fd11"}
        profile = {"id": user["id"], "full_name": "Customer", "phone": "", "role": "customer"}
        with patch.object(views, "_user", return_value=(user, None)), patch.object(views, "_profile", return_value=profile):
            response = delivery.my_delivery_orders(req)
        self.assertEqual(response.status_code, 403)

    def test_vendor_cannot_authorize_delivery_staff(self):
        from . import delivery
        req = self.factory.post("/api/delivery/staff/", {"user_id": "f2cb3c32-51d4-46aa-8ec2-785f18b7fd11"}, format="json", HTTP_AUTHORIZATION="Bearer test")
        user = {"id": "52c1edcc-bc32-44f7-b37b-f3a454617265"}
        profile = {"id": user["id"], "full_name": "Seller", "phone": "", "role": "vendor"}
        with patch.object(views, "_user", return_value=(user, None)), patch.object(views, "_profile", return_value=profile):
            response = delivery.delivery_staff(req)
        self.assertEqual(response.status_code, 403)


    def test_admin_order_list_uses_immutable_order_address_and_vendor_snapshots(self):
        req = self.factory.get("/api/orders/manage/", HTTP_AUTHORIZATION="Bearer test")
        user = {"id": "2d0f5b2c-cf10-463e-9190-ab2561a84229"}
        profile = {"id": user["id"], "full_name": "Admin", "phone": "", "role": "admin"}
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = []
        cursor.fetchall.return_value = []
        with patch.object(views, "_role_user", return_value=(user, profile, None)), \
             patch.object(views, "connection", SimpleNamespace(cursor=MagicMock(return_value=cursor))):
            response = views.manage_orders(req)

        self.assertEqual(response.status_code, 200)
        sql = cursor.execute.call_args.args[0].lower()
        self.assertIn("coalesce(o.address_snapshot, '{}'::jsonb) as address_snapshot", sql)
        self.assertIn("o.vendor_name_snapshot as vendor_name", sql)
        self.assertIn("o.vendor_address_snapshot as vendor_address", sql)
        self.assertIn("o.vendor_phone_snapshot as vendor_phone", sql)
        self.assertNotIn("from public.customer_addresses", sql)
        self.assertNotIn("v.name as vendor_name", sql)

    def test_delivery_order_list_uses_immutable_order_snapshots(self):
        from . import delivery

        req = self.factory.get("/api/delivery/orders/", HTTP_AUTHORIZATION="Bearer test")
        user = {"id": "b0e0f7e0-4b72-4d47-9ef9-a1b7c6c8e8ab"}
        profile = {"id": user["id"], "full_name": "Delivery", "phone": "", "role": "delivery_boy"}
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.description = []
        cursor.fetchall.return_value = []
        with patch.object(delivery, "_role_user", return_value=(user, profile, None)), \
             patch.object(delivery, "connection", SimpleNamespace(cursor=MagicMock(return_value=cursor))):
            response = delivery.my_delivery_orders(req)

        self.assertEqual(response.status_code, 200)
        sql = cursor.execute.call_args.args[0].lower()
        self.assertIn("o.address_snapshot as address_snapshot", sql)
        self.assertIn("o.vendor_name_snapshot as vendor_name", sql)
        self.assertIn("o.vendor_address_snapshot as vendor_address", sql)
        self.assertIn("o.vendor_phone_snapshot as vendor_phone", sql)
        self.assertIn("where o.assigned_delivery_boy_id=%s", sql)
