"""Delivery-staff assignment and fulfilment endpoints."""
import uuid

from django.db import connection, transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .views import (
    _insert_account_notification,
    _notify_admins,
    _role_user,
    _rows,
)


def _valid_uuid(value):
    try:
        return str(uuid.UUID(str(value or "").strip()))
    except (ValueError, TypeError, AttributeError):
        return None


@api_view(["GET", "POST", "DELETE"])
def delivery_staff(request):
    """Admins can list delivery staff and authorize an existing Supabase user."""
    user, profile, error = _role_user(request, {"admin"})
    if error:
        return error

    if request.method == "POST":
        staff_id = str(request.data.get("user_id") or "").strip()
        try:
            staff_id = str(uuid.UUID(staff_id))
        except (ValueError, TypeError, AttributeError):
            return Response({"detail": "Search for and select a valid existing website user."}, status=400)
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("select id from auth.users where id=%s limit 1", [staff_id])
                    auth_user = cursor.fetchone()
                    if not auth_user:
                        return Response({"detail": "No website account exists for this UUID. The person must register/sign in first."}, status=404)
                    staff_id = str(auth_user[0])
                    cursor.execute("select role from public.profiles where id=%s for update", [staff_id])
                    existing_profile = cursor.fetchone()
                    if existing_profile and existing_profile[0] in {"admin", "vendor"}:
                        return Response({"detail": "This user already has an admin/vendor role. Use a separate customer account for delivery work."}, status=409)
                    cursor.execute(
                        """insert into public.profiles(id, full_name, phone, role, is_active, availability_status)
                           values (%s, %s, %s, 'delivery_boy', true, 'offline')
                           on conflict (id) do update set
                             full_name=case when excluded.full_name<>'' then excluded.full_name else public.profiles.full_name end,
                             phone=case when excluded.phone<>'' then excluded.phone else public.profiles.phone end,
                             role='delivery_boy', is_active=true, availability_status='offline', updated_at=now()
                           returning id, full_name, phone, role, is_active, availability_status""",
                        [staff_id, str(request.data.get("full_name") or "").strip()[:120],
                         str(request.data.get("phone") or "").strip()[:30]],
                    )
                    row = cursor.fetchone()
            return Response({"id": str(row[0]), "full_name": row[1], "phone": row[2], "role": row[3], "is_active": row[4], "availability_status": row[5]}, status=201)
        except Exception:
            return Response({"detail": "Delivery staff could not be authorized. Apply the delivery-role SQL migration first."}, status=503)


    if request.method == "DELETE":
        staff_id = _valid_uuid(request.data.get("id") or request.query_params.get("id"))
        if not staff_id:
            return Response({"detail": "Choose a valid delivery staff account."}, status=400)
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("select id from public.profiles where id=%s and role='delivery_boy' for update", [staff_id])
                    if not cursor.fetchone():
                        return Response({"detail": "Delivery staff account not found."}, status=404)
                    cursor.execute("update public.orders set assigned_delivery_boy_id=NULL, updated_at=now() where assigned_delivery_boy_id=%s and status<>'delivered'", [staff_id])
                    cursor.execute("update public.profiles set role='customer', updated_at=now() where id=%s and role='delivery_boy'", [staff_id])
            return Response({"id": staff_id, "deleted": True, "role": "customer"})
        except Exception:
            return Response({"detail": "Delivery staff could not be removed. Retry after checking the database connection."}, status=503)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """select p.id, p.full_name, p.phone, u.email, coalesce(p.is_active,false) as is_active, coalesce(p.availability_status,'offline') as availability_status, p.latitude,p.longitude,p.last_location_at
                   from public.profiles p
                   left join auth.users u on u.id=p.id
                   where p.role='delivery_boy'
                   order by p.full_name, p.id
                   limit 200"""
            )
            return Response({"results": _rows(cursor)})
    except Exception:
        return Response({"detail": "Delivery staff could not be loaded. Apply the delivery-role SQL migration first."}, status=503)


@api_view(["PATCH"])
def delivery_availability(request):
    """Let an authorized delivery person pause or resume accepting new assignments."""
    user, profile, error = _role_user(request, {"delivery_boy"})
    if error:
        return error
    availability = str(request.data.get("availability_status") or "").strip().lower()
    if availability not in {"available", "offline"}:
        return Response({"detail": "Choose Available or Offline."}, status=400)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """update public.profiles
                   set availability_status=%s,
                       updated_at=now()
                   where id=%s and role='delivery_boy'
                   returning id,is_active,availability_status""",
                [availability, user["id"]],
            )
            row = cursor.fetchone()
        if not row:
            return Response({"detail": "Your delivery account is not authorized. Contact the administrator."}, status=403)
        return Response({
            "id": str(row[0]), "is_active": row[1],
            "availability_status": row[2],
            "detail": "You are now accepting deliveries." if row[2] == "available" else "You are offline and will not receive new assignments.",
        })
    except Exception:
        return Response({"detail": "Could not update your availability. Verify the delivery-role migration."}, status=503)


@api_view(["PATCH"])
def assign_delivery_staff(request):
    """Admins assign a delivery person only to a packed or dispatched order."""
    user, profile, error = _role_user(request, {"admin"})
    if error:
        return error

    order_id = _valid_uuid(request.data.get("order_id") or request.data.get("id"))
    staff_id = _valid_uuid(request.data.get("delivery_boy_id"))
    if not order_id or not staff_id:
        return Response({"detail": "Provide valid order_id and delivery_boy_id UUIDs."}, status=400)

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("""select id,full_name,is_active,availability_status from public.profiles where id=%s and role='delivery_boy' for update""", [staff_id])
                staff = cursor.fetchone()
                if not staff:
                    return Response({"detail": "Choose an authorized delivery-boy account."}, status=400)
                if staff[3] != "available":
                    return Response({"detail": "Choose a delivery person who is Online before assignment."}, status=409)
                cursor.execute(
                    """update public.orders
                       set assigned_delivery_boy_id=%s, updated_at=now()
                       where id=%s and status in ('placed','confirmed','packed','out_for_delivery')
                       returning id, order_number, status, assigned_delivery_boy_id""",
                    [staff_id, order_id],
                )
                row = cursor.fetchone()
                if not row:
                    return Response({"detail": "Order not found or not ready for delivery assignment."}, status=409)
                assignment_message = "Order " + str(row[1]) + " has been assigned to you."
                cursor.execute("""insert into public.delivery_assignment_notifications(recipient_id,order_id,order_number,message) values (%s,%s,%s,%s)""", [staff_id, str(row[0]), str(row[1]), assignment_message])
                from .push_notifications import send_push_to_user
                send_push_to_user(staff_id, "New delivery assigned", assignment_message, row[0], "delivery_assigned")
        return Response({"id": str(row[0]), "order_number": row[1], "status": row[2], "assigned_delivery_boy_id": str(row[3]), "notification_created": True})
    except Exception:
        return Response({"detail": "Could not assign delivery staff. Apply the delivery-role SQL migration first."}, status=503)


@api_view(["GET", "PATCH"])
def my_delivery_orders(request):
    """Assigned delivery staff manage preparation, dispatch, and OTP-verified completion."""
    user, profile, error = _role_user(request, {"delivery_boy"})
    if error:
        return error

    if request.method == "PATCH":
        order_id = _valid_uuid(request.data.get("order_id") or request.data.get("id"))
        next_status = str(request.data.get("status") or "").strip().lower()
        if not order_id or next_status not in {"confirmed", "cancelled", "packed"}:
            return Response({"detail": "Provide an assigned order and valid status."}, status=400)
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("""select o.id,o.order_number,o.status,o.customer_id
                        from public.orders o where o.id=%s and o.assigned_delivery_boy_id=%s for update""",
                        [order_id,user["id"]])
                    current=cursor.fetchone()
                    if not current:
                        return Response({"detail":"Order not found or not assigned to your account."},status=404)
                    transitions={"placed":{"confirmed","cancelled"},"confirmed":{"packed"},"packed":set()}
                    if next_status not in transitions.get(current[2],set()):
                        return Response({"detail":f"Order cannot move from {current[2]} to {next_status}."},status=409)
                    cursor.execute("""update public.orders set status=%s,updated_at=now()
                        where id=%s returning id,order_number,status""",[next_status,order_id])
                    updated=cursor.fetchone()
                    if next_status in {"confirmed","cancelled"}:
                        title="Order confirmed" if next_status=="confirmed" else "Order cancelled"
                        _insert_account_notification(cursor,current[3],next_status,title,
                            f"Your order {current[1]} was {next_status}.",current[0])
                        _notify_admins(cursor,next_status,title,
                            f"Order {current[1]} was {next_status} by delivery staff.",current[0])
            return Response({"id":str(updated[0]),"order_number":updated[1],"status":updated[2]})
        except Exception:
            return Response({"detail":"Order status could not be updated. Please retry."},status=503)
        if not order_id:
            return Response({"detail": "Choose a valid order."}, status=400)
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """select o.id, o.order_number, o.status, o.payment_method,
                                  o.payment_status, o.customer_id
                           from public.orders o
                           where o.id=%s and o.assigned_delivery_boy_id=%s
                           for update""",
                        [order_id, user["id"]],
                    )
                    order = cursor.fetchone()
                    if not order:
                        return Response({"detail": "Order not found or not assigned to your account."}, status=404)
                    if order[2] != "out_for_delivery":
                        return Response({"detail": "Only orders marked out for delivery can be completed."}, status=409)
                    cursor.execute(
                        """update public.orders
                           set status='delivered',
                               payment_status=case
                                 when payment_method='cod' and payment_status='pending' then 'paid'
                                 else payment_status end,
                               updated_at=now()
                           where id=%s
                           returning id, order_number, status, payment_status, total, created_at""",
                        [order_id],
                    )
                    updated = cursor.fetchone()
                    _insert_account_notification(
                        cursor, order[5], "delivered", "Your order was delivered",
                        f"Order {order[1]} has been delivered.", order[0],
                    )
                    _notify_admins(
                        cursor, "delivered", "Order delivered",
                        f"Order {order[1]} has been delivered by delivery staff.", order[0],
                    )
            return Response({
                "id": str(updated[0]), "order_number": updated[1], "status": updated[2],
                "payment_status": updated[3], "total": str(updated[4]),
                "created_at": updated[5].isoformat() if hasattr(updated[5], "isoformat") else updated[5],
            })
        except Exception:
            return Response({"detail": "Delivery status could not be updated. Please retry."}, status=503)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """select o.id, o.order_number, o.status, o.payment_method, o.payment_status,
                          o.subtotal, o.delivery_fee, o.total,
                          (coalesce(
                            (select jsonb_build_object(
                              'recipient_name',ca.recipient_name,'phone',ca.phone,
                              'line1',ca.line1,'line2',ca.line2,'landmark',ca.landmark,
                              'city',ca.city,'state',ca.state,'postal_code',ca.postal_code,
                              'latitude',ca.latitude,'longitude',ca.longitude
                            ) from public.customer_addresses ca
                             where ca.user_id=o.customer_id
                             order by ca.is_default desc,ca.updated_at desc,ca.created_at desc limit 1),
                            '{}'::jsonb
                          ) || (
                            coalesce(nullif(o.address_snapshot,'{}'::jsonb), '{}'::jsonb)
                            - ARRAY(
                              select e.key from jsonb_each(coalesce(o.address_snapshot,'{}'::jsonb)) as e(key,value)
                              where e.value='null'::jsonb
                                 or (jsonb_typeof(e.value)='string' and btrim(e.value #>> '{}')='')
                            )
                          )) as address_snapshot, o.notes,
                          o.created_at, v.name as vendor_name, v.address as vendor_address,
                          v.phone as vendor_phone, cu.email as customer_email,
                          coalesce(json_agg(json_build_object(
                            'product_name', oi.product_name, 'image_url', oi.image_url,
                            'quantity', oi.quantity, 'size', oi.size, 'color', oi.color,
                            'unit_price', oi.unit_price, 'line_total', oi.line_total
                          )) filter (where oi.id is not null), '[]'::json) as items
                   from public.orders o
                   join public.vendors v on v.id=o.vendor_id
                   left join auth.users cu on cu.id=o.customer_id
                   left join public.order_items oi on oi.order_id=o.id
                   where o.assigned_delivery_boy_id=%s
                   group by o.id, v.name, v.address, v.phone, cu.email
                   order by case o.status when 'out_for_delivery' then 0 when 'packed' then 1 else 2 end,
                            o.created_at desc
                   limit 100""",
                [user["id"]],
            )
            rows = _rows(cursor)
            cursor.execute("""select id,order_number,message,created_at from public.delivery_assignment_notifications
                where recipient_id=%s and read_at is null order by created_at desc limit 20""", [user["id"]])
            notifications = _rows(cursor)
            if notifications:
                cursor.execute("update public.delivery_assignment_notifications set read_at=now() where recipient_id=%s and read_at is null", [user["id"]])
            cursor.execute("select coalesce(is_active,false),coalesce(availability_status,'offline') from public.profiles where id=%s and role='delivery_boy'", [user["id"]])
            availability_row = cursor.fetchone()
        return Response({
            "results": rows, "count": len(rows), "notifications": notifications,
            "is_active": bool(availability_row[0]) if availability_row else False,
            "availability_status": availability_row[1] if availability_row else "offline",
        })
    except Exception:
        return Response({"detail": "Assigned deliveries could not be loaded. Apply the delivery-role SQL migration first."}, status=503)

@api_view(["POST"])
def delivery_location(request):
    """Save the active delivery person's latest GPS location and availability."""
    user, profile, error = _role_user(request, {"delivery_boy"})
    if error:
        return error
    try:
        latitude = float(request.data.get("latitude"))
        longitude = float(request.data.get("longitude"))
    except (TypeError, ValueError):
        return Response({"detail": "Valid latitude and longitude are required."}, status=400)
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return Response({"detail": "GPS coordinates are outside valid ranges."}, status=400)
    availability = str(request.data.get("availability_status") or "available").strip().lower()
    if availability not in {"available", "offline"}:
        return Response({"detail": "Choose Online or Offline."}, status=400)
    try:
        with connection.cursor() as cursor:
            cursor.execute("""update public.profiles set latitude=%s,longitude=%s,last_location_at=now(),
                availability_status=%s,updated_at=now()
                where id=%s and role='delivery_boy'
                returning id,availability_status,last_location_at""",
                [latitude, longitude, availability, user["id"]])
            row = cursor.fetchone()
        if not row:
            return Response({"detail": "Your delivery account is not authorized. Contact the administrator."}, status=403)
        return Response({"id": str(row[0]), "availability_status": row[1], "last_location_at": row[2].isoformat()})
    except Exception:
        return Response({"detail": "Location could not be saved. Apply the delivery assignment migration."}, status=503)
