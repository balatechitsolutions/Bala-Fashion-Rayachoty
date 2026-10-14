"""Safe order-address repair for incomplete historical snapshots."""
import math
import json
import re
import uuid

from django.utils import timezone

from django.db import connection, transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .views import _role_user

PHONE_RE = re.compile(r"^[0-9+() -]{10,16}$")


def _valid_coordinates(data):
    try:
        lat = float(data.get("latitude"))
        lng = float(data.get("longitude"))
    except (TypeError, ValueError, OverflowError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


@api_view(["PATCH"])
def repair_order_address(request):
    """Only administrators can correct an order address; every correction is audited."""
    user, profile, error = _role_user(request, {"admin"})
    if error:
        return error
    data = request.data
    try:
        order_id = str(uuid.UUID(str(data.get("order_id") or "")))
    except (ValueError, TypeError, AttributeError):
        return Response({"detail": "Choose a valid order."}, status=400)

    recipient = str(data.get("recipient_name") or "").strip()[:120]
    phone = str(data.get("phone") or "").strip()[:30]
    line1 = str(data.get("line1") or "").strip()[:200]
    line2 = str(data.get("line2") or "").strip()[:200]
    landmark = str(data.get("landmark") or "").strip()[:160]
    city = str(data.get("city") or "Rayachoty").strip()[:100]
    state = str(data.get("state") or "Andhra Pradesh").strip()[:100]
    postal_code = str(data.get("postal_code") or "").strip()[:12]
    coords = _valid_coordinates(data)
    if not recipient or not PHONE_RE.fullmatch(phone) or sum(ch.isdigit() for ch in phone) < 10 or sum(ch.isdigit() for ch in phone) > 15 or not line1:
        return Response({"detail": "Enter the recipient name, valid phone number and house/street address."}, status=400)
    if city.casefold() not in {"rayachoty", "rayachoti"}:
        return Response({"detail": "Bala Fashion currently delivers only within Rayachoty."}, status=400)
    if not coords:
        return Response({"detail": "Choose a valid delivery location using the map or current-location button."}, status=400)

    is_admin = profile["role"] == "admin"
    correction_reason = str(data.get("correction_reason") or "").strip()[:500]
    if not correction_reason:
        return Response({"detail": "An audit reason is required for an order-address correction."}, status=400)
    supplied = {
        "recipient_name": recipient, "phone": phone, "line1": line1,
        "line2": line2, "landmark": landmark, "city": "Rayachoty",
        "state": "Andhra Pradesh", "postal_code": postal_code,
        "latitude": coords[0], "longitude": coords[1],
    }
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                """select customer_id, status, coalesce(address_snapshot, '{}'::jsonb)
                   from public.orders where id=%s for update""",
                [order_id],
            )
            order = cursor.fetchone()
            if not order:
                return Response({"detail": "Order not found."}, status=404)
            # Delivered/cancelled orders are immutable history. Correct only active
            # orders that may still be delivered, before delivery dispatch starts.
            if order[1] in {"out_for_delivery", "delivered", "cancelled"}:
                return Response({"detail": "This order can no longer be address-corrected because delivery has started or the order is closed."}, status=409)
            snapshot = order[2] if isinstance(order[2], dict) else {}
            repaired = dict(snapshot)
            repaired.update(supplied)
            repaired["address_completion_source"] = "admin_corrected"
            repaired["address_completed_at"] = timezone.now().isoformat()
            cursor.execute(
                """insert into public.order_address_audit
                   (order_id, changed_by, correction_reason, previous_address, corrected_address)
                   values (%s, %s, %s, %s::jsonb, %s::jsonb)""",
                [order_id, user["id"], correction_reason, json.dumps(snapshot), json.dumps(repaired)],
            )
            cursor.execute(
                "update public.orders set address_snapshot=%s::jsonb, updated_at=now() where id=%s",
                [json.dumps(repaired), order_id],
            )
        return Response({"order_id": order_id, "address_snapshot": repaired,
                         "detail": "Order delivery address corrected and audit record saved."})
    except Exception:
        return Response({"detail": "Could not update this delivery address. Please retry."}, status=503)
