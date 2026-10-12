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


@api_view(["GET", "POST"])
def delivery_staff(request):
    """Admins can list delivery staff and authorize an existing Supabase user."""
    user, profile, error = _role_user(request, {"admin"})
    if error:
        return error

    if request.method == "POST":
        staff_id = _valid_uuid(request.data.get("user_id"))
        if not staff_id:
            return Response({"detail": "Enter a valid Supabase Auth user UUID."}, status=400)
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("select id from auth.users where id=%s", [staff_id])
                    if not cursor.fetchone():
                        return Response({"detail": "No Supabase Auth user exists for that UUID."}, status=404)
                    cursor.execute("select role from public.profiles where id=%s for update", [staff_id])
                    existing_profile = cursor.fetchone()
                    if existing_profile and existing_profile[0] in {"admin", "vendor"}:
                        return Response({"detail": "This user already has an admin/vendor role. Use a separate customer account for delivery work."}, status=409)
                    cursor.execute(
                        """insert into public.profiles(id, full_name, phone, role)
                           values (%s, %s, %s, 'delivery_boy')
                           on conflict (id) do update set
                             full_name=case when excluded.full_name<>'' then excluded.full_name else public.profiles.full_name end,
                             phone=case when excluded.phone<>'' then excluded.phone else public.profiles.phone end,
                             role='delivery_boy', updated_at=now()
                           returning id, full_name, phone, role""",
                        [staff_id, str(request.data.get("full_name") or "").strip()[:120],
                         str(request.data.get("phone") or "").strip()[:30]],
                    )
                    row = cursor.fetchone()
            return Response({"id": str(row[0]), "full_name": row[1], "phone": row[2], "role": row[3]}, status=201)
        except Exception:
            return Response({"detail": "Delivery staff could not be authorized. Apply the delivery-role SQL migration first."}, status=503)

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """select p.id, p.full_name, p.phone
                   from public.profiles p
                   where p.role='delivery_boy'
                   order by p.full_name, p.id
                   limit 200"""
            )
            return Response({"results": _rows(cursor)})
    except Exception:
        return Response({"detail": "Delivery staff could not be loaded. Apply the delivery-role SQL migration first."}, status=503)


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
                cursor.execute("select id from public.profiles where id=%s and role='delivery_boy'", [staff_id])
                if not cursor.fetchone():
                    return Response({"detail": "Choose an authorized delivery-boy account."}, status=400)
                cursor.execute(
                    """update public.orders
                       set assigned_delivery_boy_id=%s, updated_at=now()
                       where id=%s and status in ('packed','out_for_delivery')
                       returning id, order_number, status, assigned_delivery_boy_id""",
                    [staff_id, order_id],
                )
                row = cursor.fetchone()
                if not row:
                    return Response({"detail": "Order not found or it must be packed/out for delivery before assignment."}, status=409)
        return Response({"id": str(row[0]), "order_number": row[1], "status": row[2], "assigned_delivery_boy_id": str(row[3])})
    except Exception:
        return Response({"detail": "Could not assign delivery staff. Apply the delivery-role SQL migration first."}, status=503)


@api_view(["GET", "PATCH"])
def my_delivery_orders(request):
    """Delivery staff can view only assigned orders and mark their dispatched orders delivered."""
    user, profile, error = _role_user(request, {"delivery_boy"})
    if error:
        return error

    if request.method == "PATCH":
        order_id = _valid_uuid(request.data.get("order_id") or request.data.get("id"))
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
                          o.subtotal, o.delivery_fee, o.total, o.address_snapshot, o.notes,
                          o.created_at, v.name as vendor_name,
                          coalesce(json_agg(json_build_object(
                            'product_name', oi.product_name, 'image_url', oi.image_url,
                            'quantity', oi.quantity, 'size', oi.size, 'color', oi.color,
                            'line_total', oi.line_total
                          )) filter (where oi.id is not null), '[]'::json) as items
                   from public.orders o
                   join public.vendors v on v.id=o.vendor_id
                   left join public.order_items oi on oi.order_id=o.id
                   where o.assigned_delivery_boy_id=%s
                   group by o.id, v.name
                   order by case o.status when 'out_for_delivery' then 0 when 'packed' then 1 else 2 end,
                            o.created_at desc
                   limit 100""",
                [user["id"]],
            )
            rows = _rows(cursor)
        return Response({"results": rows, "count": len(rows)})
    except Exception:
        return Response({"detail": "Assigned deliveries could not be loaded. Apply the delivery-role SQL migration first."}, status=503)
