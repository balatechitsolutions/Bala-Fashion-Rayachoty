import re
import uuid

from django.db import connection, transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .views import _user

PHONE_RE = re.compile(r"^[0-9+() \-]{10,16}$")


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
                    f"select {SELECT_FIELDS} from public.customer_addresses where user_id=%s order by is_default desc, created_at desc",
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
        with connection.cursor() as cursor:
            cursor.execute("select id,is_default from public.customer_addresses where id=%s and user_id=%s", [address_id, user_id])
            existing = cursor.fetchone()
        if not existing:
            return Response({"detail": "Address not found in your account."}, status=404)
        if request.method == "DELETE":
            try:
                with transaction.atomic(), connection.cursor() as cursor:
                    cursor.execute("delete from public.customer_addresses where id=%s and user_id=%s returning is_default", [address_id, user_id])
                    deleted = cursor.fetchone()
                    if deleted and deleted[0]:
                        cursor.execute(
                            "update public.customer_addresses set is_default=true where id=(select id from public.customer_addresses where user_id=%s order by created_at desc limit 1)",
                            [user_id],
                        )
                return Response({"id": address_id, "detail": "Address deleted."})
            except Exception:
                return Response({"detail": "Address could not be deleted."}, status=503)

    data = request.data
    recipient = str(data.get("recipient_name", "")).strip()[:120]
    phone = str(data.get("phone", "")).strip()[:30]
    line1 = str(data.get("line1", "")).strip()[:200]
    city = str(data.get("city", "Rayachoty")).strip()[:100] or "Rayachoty"
    state = str(data.get("state", "Andhra Pradesh")).strip()[:100] or "Andhra Pradesh"
    postal_code = str(data.get("postal_code", "")).strip()[:12]
    if not recipient or not line1 or not PHONE_RE.fullmatch(phone):
        return Response({"detail": "Enter recipient name, valid mobile number and house/street address."}, status=400)
    if city.casefold() not in {"rayachoty", "rayachoti"}:
        return Response({"detail": "Bala Fashion currently delivers only within Rayachoty."}, status=400)
    try:
        latitude = float(data.get("latitude"))
        longitude = float(data.get("longitude"))
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise ValueError()
    except (TypeError, ValueError):
        return Response({"detail": "Choose a valid map location for this address."}, status=400)
    is_default = bool(data.get("is_default", False))
    fields = [
        recipient, phone, line1, str(data.get("line2", "")).strip()[:200],
        str(data.get("landmark", "")).strip()[:160], "Rayachoty", "Andhra Pradesh",
        postal_code, latitude, longitude, str(data.get("notes", "")).strip()[:500],
    ]
    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("select id from public.customer_addresses where user_id=%s for update", [user_id])
            has_addresses = bool(cursor.fetchone())
            if request.method == "POST":
                is_default = is_default or not has_addresses
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
                if is_default:
                    cursor.execute("update public.customer_addresses set is_default=false where user_id=%s", [user_id])
                cursor.execute(
                    """update public.customer_addresses set
                       recipient_name=%s,phone=%s,line1=%s,line2=%s,landmark=%s,city=%s,state=%s,
                       postal_code=%s,latitude=%s,longitude=%s,notes=%s,is_default=%s,updated_at=now()
                       where id=%s and user_id=%s returning """ + SELECT_FIELDS,
                    [*fields, is_default, address_id, user_id],
                )
            row = cursor.fetchone()
        if not row:
            return Response({"detail": "Address could not be saved."}, status=404)
        return Response(_address_payload(row), status=201 if request.method == "POST" else 200)
    except Exception:
        return Response({"detail": "Address could not be saved. Check the customer-address SQL migration."}, status=503)
