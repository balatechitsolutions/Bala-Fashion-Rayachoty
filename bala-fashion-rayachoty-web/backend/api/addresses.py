import math
import re
import uuid

from django.db import connection, transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .views import _user

PHONE_RE = re.compile(r"^[0-9+() \-]{10,16}$")


def _valid_phone(value):
    phone = str(value or "").strip()
    digits = sum(character.isdigit() for character in phone)
    return bool(PHONE_RE.fullmatch(phone) and 10 <= digits <= 15)


def _address_payload(row):
    return {
        "id": str(row[0]), "recipient_name": row[1], "phone": row[2],
        "line1": row[3], "line2": row[4] or "", "landmark": row[5] or "",
        "city": row[6], "state": row[7], "postal_code": row[8] or "",
        "latitude": row[9], "longitude": row[10], "notes": row[11] or "",
        "is_default": bool(row[12]), "created_at": row[13].isoformat() if row[13] else None,
    }


SELECT_FIELDS = """id,recipient_name,phone,line1,line2,landmark,city,state,postal_code,
                   latitude,longitude,notes,is_default,created_at"""


def _ensure_customer_default(cursor, user_id):
    """Ensure an account with saved addresses has exactly one default."""
    cursor.execute(
        """select id from public.customer_addresses where user_id=%s and is_default=true
           order by updated_at desc, created_at desc limit 1""",
        [user_id],
    )
    if cursor.fetchone():
        return
    cursor.execute(
        """update public.customer_addresses set is_default=true
           where id=(select id from public.customer_addresses where user_id=%s
                     order by updated_at desc, created_at desc limit 1)""",
        [user_id],
    )


@api_view(["GET", "POST", "PATCH", "DELETE"])
def customer_addresses(request):
    user, error = _user(request)
    if error:
        return error
    user_id = user["id"]
    address_id = str(request.data.get("id") or request.query_params.get("id") or "").strip()

    if request.method == "GET":
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"select {SELECT_FIELDS} from public.customer_addresses where user_id=%s order by is_default desc, updated_at desc, created_at desc",
                    [user_id],
                )
                rows = cursor.fetchall()
            return Response({"results": [_address_payload(row) for row in rows]})
        except Exception:
            return Response({"detail": "Saved addresses are unavailable. Apply the customer-address SQL migration."}, status=503)

    if request.method in {"PATCH", "DELETE"}:
        try:
            uuid.UUID(address_id)
        except (ValueError, TypeError, AttributeError):
            return Response({"detail": "Choose a valid saved address."}, status=400)

    data = request.data
    if request.method == "DELETE":
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("select id from public.customer_addresses where user_id=%s for update", [user_id])
                cursor.fetchall()
                cursor.execute(
                    "delete from public.customer_addresses where id=%s and user_id=%s returning id",
                    [address_id, user_id],
                )
                deleted = cursor.fetchone()
                if not deleted:
                    return Response({"detail": "Address not found in your account."}, status=404)
                _ensure_customer_default(cursor, user_id)
            return Response({"id": address_id, "detail": "Address deleted."})
        except Exception:
            return Response({"detail": "Address could not be deleted."}, status=503)

    if request.method == "PATCH":
        with connection.cursor() as cursor:
            cursor.execute("select id from public.customer_addresses where id=%s and user_id=%s", [address_id, user_id])
            if not cursor.fetchone():
                return Response({"detail": "Address not found in your account."}, status=404)

    recipient = str(data.get("recipient_name", "")).strip()[:120]
    phone = str(data.get("phone", "")).strip()[:30]
    line1 = str(data.get("line1", "")).strip()[:200]
    city = str(data.get("city", "Rayachoty")).strip()[:100] or "Rayachoty"
    postal_code = str(data.get("postal_code", "")).strip()[:12]
    if not recipient or not line1 or not _valid_phone(phone):
        return Response({"detail": "Enter recipient name, a valid 10–15 digit contact number, and house/street address."}, status=400)
    if city.casefold() not in {"rayachoty", "rayachoti"}:
        return Response({"detail": "Bala Fashion currently delivers only within Rayachoty."}, status=400)
    try:
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
        if not (math.isfinite(latitude) and math.isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError()
    except (TypeError, ValueError, OverflowError):
        return Response({"detail": "Choose a valid map location for this address."}, status=400)

    requested_default = bool(data.get("is_default", False))
    fields = [
        recipient, phone, line1, str(data.get("line2", "")).strip()[:200],
        str(data.get("landmark", "")).strip()[:160], "Rayachoty", "Andhra Pradesh",
        postal_code, latitude, longitude, str(data.get("notes", "")).strip()[:500],
    ]
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            # Serialize changes per customer so concurrent requests cannot create
            # two defaults for the same account.
            cursor.execute("select id from public.customer_addresses where user_id=%s for update", [user_id])
            existing_rows = cursor.fetchall()
            has_other_addresses = any(str(row[0]) != address_id for row in existing_rows)
            if request.method == "POST":
                is_default = requested_default or not existing_rows
                if is_default:
                    cursor.execute("update public.customer_addresses set is_default=false where user_id=%s", [user_id])
                cursor.execute(
                    """insert into public.customer_addresses
                       (user_id,recipient_name,phone,line1,line2,landmark,city,state,postal_code,latitude,longitude,notes,is_default)
                       values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       returning """ + SELECT_FIELDS,
                    [user_id, *fields, is_default],
                )
            else:
                cursor.execute("select is_default from public.customer_addresses where id=%s and user_id=%s", [address_id, user_id])
                existing = cursor.fetchone()
                if not existing:
                    return Response({"detail": "Address not found in your account."}, status=404)
                was_default = bool(existing[0])
                is_default = requested_default or (was_default and not has_other_addresses)
                if is_default:
                    cursor.execute("update public.customer_addresses set is_default=false where user_id=%s", [user_id])
                cursor.execute(
                    """update public.customer_addresses set
                       recipient_name=%s,phone=%s,line1=%s,line2=%s,landmark=%s,city=%s,state=%s,
                       postal_code=%s,latitude=%s,longitude=%s,notes=%s,is_default=%s,updated_at=now()
                       where id=%s and user_id=%s returning """ + SELECT_FIELDS,
                    [*fields, is_default, address_id, user_id],
                )
                # If the previous default was explicitly unset, select another
                # saved address rather than leaving the customer without one.
                if was_default and not is_default:
                    _ensure_customer_default(cursor, user_id)
            row = cursor.fetchone()
            if row and not row[12]:
                _ensure_customer_default(cursor, user_id)
                cursor.execute(f"select {SELECT_FIELDS} from public.customer_addresses where id=%s and user_id=%s", [row[0], user_id])
                row = cursor.fetchone()
        if not row:
            return Response({"detail": "Address could not be saved."}, status=404)
        return Response(_address_payload(row), status=201 if request.method == "POST" else 200)
    except Exception:
        return Response({"detail": "Address could not be saved. Check the customer-address SQL migration."}, status=503)
