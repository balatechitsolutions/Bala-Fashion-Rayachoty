"""Safe order-address repair for incomplete historical snapshots."""
import math
import re
import uuid

from django.db import connection, transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .views import _role_user

PHONE_RE = re.compile(r"^[0-9+() \\-]{10,16}$")


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
    """Customers fill missing fields on their own order; admins can correct a snapshot."""
    user, profile, error = _role_user(request, {"customer", "admin"})
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
    replace_existing = is_admin and data.get("replace_existing") is True
    supplied = {
        "recipient_name": recipient, "phone": phone, "line1": line1,
        "line2": line2, "landmark": landmark, "city": "Rayachoty",
        "state": "Andhra Pradesh", "postal_code": postal_code,
        "latitude": coords[0], "longitude": coords[1],
    }
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                """select customer_id, coalesce(address_snapshot, '{}'::jsonb)
                   from public.orders where id=%s for update""",
                [order_id],
            )
            order = cursor.fetchone()
            if not order:
                return Response({"detail": "Order not found."}, status=404)
            if not is_admin and str(order[0]) != str(user["id"]):
                return Response({"detail": "You can only repair the address on your own orders."}, status=403)
            snapshot = order[1] if isinstance(order[1], dict) else {}
            repaired = dict(snapshot)
            for key, value in supplied.items():
                existing = repaired.get(key)
                missing = existing is None or (isinstance(existing, str) and not existing.strip())
                if replace_existing or missing:
                    repaired[key] = value
            repaired["address_completion_source"] = "admin_corrected" if replace_existing else "customer_supplied"
            repaired["address_completed_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
            cursor.execute(
                "update public.orders set address_snapshot=%s::jsonb, updated_at=now() where id=%s",
                [__import__("json").dumps(repaired), order_id],
            )
            # Keep the customer's saved address in sync only when this snapshot
            # already points to an address owned by the same customer.
            saved_id = str(snapshot.get("saved_address_id") or "")
            try:
                saved_id = str(uuid.UUID(saved_id))
            except (ValueError, TypeError, AttributeError):
                saved_id = ""
            if saved_id and not is_admin:
                cursor.execute(
                    """update public.customer_addresses set recipient_name=%s, phone=%s, line1=%s,
                       line2=%s, landmark=%s, city=%s, state=%s, postal_code=%s,
                       latitude=%s, longitude=%s, updated_at=now()
                       where id=%s and user_id=%s""",
                    [recipient, phone, line1, line2, landmark, "Rayachoty", "Andhra Pradesh",
                     postal_code, coords[0], coords[1], saved_id, user["id"]],
                )
        return Response({"order_id": order_id, "address_snapshot": repaired,
                         "detail": "Delivery address updated. Delivery can start only after all required fields are complete."})
    except Exception:
        return Response({"detail": "Could not update this delivery address. Please retry."}, status=503)
