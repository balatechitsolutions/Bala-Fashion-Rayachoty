import json, os, re, uuid
from decimal import Decimal, InvalidOperation, ROUND_CEILING
import requests
from django.db import connection, transaction
from django.core.cache import cache
import hashlib
import logging
from django.utils.text import slugify
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from cloudinary.utils import api_sign_request

SUPABASE_URL=os.getenv("SUPABASE_URL","").rstrip("/")
SUPABASE_KEY=os.getenv("SUPABASE_PUBLISHABLE_KEY","")
CLOUD_NAME=os.getenv("CLOUDINARY_CLOUD_NAME","")
CLOUD_KEY=os.getenv("CLOUDINARY_API_KEY","")
CLOUD_SECRET=os.getenv("CLOUDINARY_API_SECRET","")
MAX_DELIVERY_DISTANCE_METERS = 5000
RAYACHOTI_BUS_STAND_LATITUDE = 14.05742
RAYACHOTI_BUS_STAND_LONGITUDE = 78.74865
DELIVERY_BLOCK_METERS = 500
DELIVERY_BLOCK_FEE = Decimal("5.00")
DEFAULT_OSRM_BASE_URL = "https://router.project-osrm.org"

def _coordinate(value, name):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"Choose a valid map location for {name}.")
    limit = 90 if name == "latitude" else 180
    if not (-limit <= result <= limit):
        raise ValueError(f"Choose a valid map location for {name}.")
    return result

def _order_address_issues(address):
    """Return missing/invalid fields that make an order unsafe to hand to delivery.

    PostgreSQL JSONB normally arrives as a dict, but some database driver/config
    combinations return serialized JSON text. Normalize both forms before
    validation so a complete immutable order snapshot is not falsely rejected.
    """
    if isinstance(address, str):
        try:
            address = json.loads(address)
        except (TypeError, ValueError, json.JSONDecodeError):
            return ["saved order delivery address"]
    if not isinstance(address, dict):
        return ["saved order delivery address"]
    issues = []
    recipient = str(address.get("recipient_name") or "").strip()
    phone = str(address.get("phone") or "").strip()
    line1 = str(address.get("line1") or "").strip()
    digits = sum(character.isdigit() for character in phone)
    if not recipient:
        issues.append("recipient name")
    if not (re.fullmatch(r"[0-9+() \-]{10,16}", phone) and 10 <= digits <= 15):
        issues.append("valid recipient phone number")
    if not line1:
        issues.append("house/street address")
    city = str(address.get("city") or "").strip().casefold()
    if city not in {"rayachoty", "rayachoti"}:
        issues.append("Rayachoty delivery city")
    try:
        _coordinate(address.get("latitude"), "latitude")
        _coordinate(address.get("longitude"), "longitude")
    except ValueError:
        issues.append("valid map coordinates")
    return issues

def delivery_fee_for_distance(distance_meters):
    """Charge ₹5 for each started 500-metre road-distance block."""
    try:
        distance = Decimal(str(distance_meters))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Could not calculate the delivery distance.")
    if not distance.is_finite() or distance < 0:
        raise ValueError("Could not calculate the delivery distance.")
    blocks = (distance / Decimal(DELIVERY_BLOCK_METERS)).to_integral_value(rounding=ROUND_CEILING)
    return (blocks * DELIVERY_BLOCK_FEE).quantize(Decimal("0.01"))

def road_distance_meters(origin_latitude, origin_longitude, destination_latitude, destination_longitude):
    """Ask OSRM for driving-route distance; straight-line distance is never used for pricing."""
    base_url = os.getenv("OSRM_BASE_URL", DEFAULT_OSRM_BASE_URL).rstrip("/")
    url = (
        f"{base_url}/route/v1/driving/"
        f"{origin_longitude},{origin_latitude};{destination_longitude},{destination_latitude}"
    )
    try:
        response = requests.get(
            url,
            params={"overview": "false", "alternatives": "false", "steps": "false"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RuntimeError("Road-distance service is temporarily unavailable. Please retry.") from exc
    routes = payload.get("routes") or []
    if payload.get("code") != "Ok" or not routes or routes[0].get("distance") is None:
        raise ValueError("A drivable route could not be found for this delivery location.")
    distance = float(routes[0]["distance"])
    if not distance >= 0 or distance != distance or distance == float("inf"):
        raise ValueError("Could not calculate the delivery distance.")
    return distance

def _rows_from_dicts(rows):
    """Normalize UUID/date values for JSON responses."""
    normalized = []
    for row in rows:
        item = dict(row)
        for key, value in item.items():
            if isinstance(value, uuid.UUID):
                item[key] = str(value)
            elif hasattr(value, "isoformat"):
                item[key] = value.isoformat()
        normalized.append(item)
    return normalized

def _rows(cursor):
    cols=[c[0] for c in cursor.description]
    out=[]
    for row in cursor.fetchall():
        d=dict(zip(cols,row))
        for k,v in list(d.items()):
            if isinstance(v,Decimal): d[k]=str(v)
            elif hasattr(v,"isoformat"): d[k]=v.isoformat()
        out.append(d)
    return out

def _user(request):
    header=request.headers.get("Authorization","")
    if not header.startswith("Bearer "): return None,Response({"detail":"Sign in to continue."},status=401)
    if not SUPABASE_URL or not SUPABASE_KEY: return None,Response({"detail":"Supabase authentication is not configured."},status=503)
    try:
        r=requests.get(f"{SUPABASE_URL}/auth/v1/user",headers={"apikey":SUPABASE_KEY,"Authorization":header},timeout=8)
    except requests.RequestException:
        return None,Response({"detail":"Authentication service is temporarily unavailable."},status=503)
    if r.status_code!=200: return None,Response({"detail":"Your session expired. Please sign in again."},status=401)
    return r.json(),None

def _profile(user_id):
    with connection.cursor() as c:
        c.execute("select id,full_name,phone,role from public.profiles where id=%s",[user_id])
        row=c.fetchone()
    return {"id":str(row[0]),"full_name":row[1],"phone":row[2],"role":row[3]} if row else {"id":str(user_id),"full_name":"","phone":"","role":"customer"}


def _resolve_order_address(cursor, user_id, requested_address_id=""):
    """Load an address owned by this customer; never trust checkout address fields."""
    fields = (
        "id", "recipient_name", "phone", "line1", "line2", "landmark", "city",
        "state", "postal_code", "latitude", "longitude", "notes",
    )
    requested_address_id = str(requested_address_id or "").strip()
    if requested_address_id:
        try:
            requested_address_id = str(uuid.UUID(requested_address_id))
        except (ValueError, TypeError, AttributeError):
            raise ValueError("Choose a valid saved delivery address.")
        cursor.execute(
            """select id,recipient_name,phone,line1,line2,landmark,city,state,postal_code,
                      latitude,longitude,notes
               from public.customer_addresses where id=%s and user_id=%s
               for share""",
            [requested_address_id, user_id],
        )
    else:
        cursor.execute(
            """select id,recipient_name,phone,line1,line2,landmark,city,state,postal_code,
                      latitude,longitude,notes
               from public.customer_addresses
               where user_id=%s and is_default=true
               order by updated_at desc, created_at desc limit 1
               for share""",
            [user_id],
        )
    row = cursor.fetchone()
    if not row:
        if requested_address_id:
            raise ValueError("Selected saved address was not found in your account. Choose one of your saved addresses.")
        raise ValueError("No default delivery address is saved. Add an address and mark it as default before placing an order.")
    resolved = dict(zip(fields, row))
    resolved["id"] = str(resolved["id"])
    return resolved


def _insert_account_notification(cursor, recipient_id, event_type, title, body, order_id):
    """Persist one account-scoped notification; uniqueness prevents duplicate events."""
    if not recipient_id:
        return
    cursor.execute(
        """insert into public.account_notifications
               (id, recipient_id, event_type, title, body, order_id)
           values (%s, %s, %s, %s, %s, %s)
           on conflict (recipient_id, order_id, event_type) do nothing""",
        [str(uuid.uuid4()), str(recipient_id), event_type, title, body, str(order_id)],
    )
    if cursor.rowcount == 1:
        # Dispatch after commit. Redis/Celery moves push delivery to a worker; when
        # Redis is absent, preserve the existing best-effort inline behavior.
        def dispatch_push():
            try:
                if os.getenv("CELERY_BROKER_URL", "").strip():
                    from .tasks import send_account_push
                    send_account_push.delay(
                        str(recipient_id), title, body, str(order_id), event_type
                    )
                else:
                    from .push_notifications import send_push_to_user
                    send_push_to_user(recipient_id, title, body, order_id, event_type)
            except Exception:
                logging.getLogger(__name__).exception("Could not dispatch account notification push")
        transaction.on_commit(dispatch_push)


def _notify_admins(cursor, event_type, title, body, order_id):
    cursor.execute("select id from public.profiles where role='admin'")
    for (admin_id,) in cursor.fetchall():
        _insert_account_notification(cursor, admin_id, event_type, title, body, order_id)

def _role_user(request,roles):
    user,error=_user(request)
    if error:return None,None,error
    prof=_profile(user["id"])
    if prof["role"] not in roles:return user,prof,Response({"detail":"Your account does not have permission for this action."},status=403)
    return user,prof,None

@api_view(["GET"])
def health(request):
    """Expose service health without disclosing internal database configuration."""
    try:
        if not os.getenv("DATABASE_URL"):
            return Response({"status": "ok"})
        with connection.cursor() as c:
            c.execute("select 1")
            c.fetchone()
        return Response({"status": "ok"})
    except Exception:
        # Keep infrastructure details in server logs, not public responses.
        logging.warning("Health check failed: database connectivity unavailable")
        return Response({"status": "degraded"}, status=503)

@api_view(["GET"])
def manage_auth_users(request):
    """List existing Supabase Auth accounts for admins to assign vendor/delivery roles."""
    user, profile, error = _role_user(request, {"admin"})
    if error:
        return error
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT u.id, u.email,
                       COALESCE(NULLIF(p.full_name, ''), u.raw_user_meta_data->>'full_name', '') AS full_name,
                       COALESCE(p.phone, '') AS phone,
                       COALESCE(p.role, 'customer') AS role,
                       u.created_at
                FROM auth.users u
                LEFT JOIN public.profiles p ON p.id = u.id
                ORDER BY u.created_at DESC
                LIMIT 1000
                """
            )
            columns = [column[0] for column in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        return Response({"results": _rows_from_dicts(rows), "count": len(rows)})
    except Exception:
        return Response(
            {"detail": "Website users could not be fetched. Verify the backend database connection and auth.users permissions."},
            status=503,
        )


@api_view(["GET"])
def categories(request):
    cache_key = "catalog:categories:v3"
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)
    try:
        with connection.cursor() as c:
            c.execute("""
                select c.id,c.name,c.slug,c.image_url,c.sort_order,c.parent_id,
                       p.name as parent_name,p.slug as parent_slug
                from public.categories c
                left join public.categories p on p.id=c.parent_id
                where c.is_active=true
                order by coalesce(p.sort_order,c.sort_order),p.name,c.sort_order,c.name
            """)
            rows = _rows(c)
        cache.set(cache_key, rows, 60)
        return Response(rows)
    except Exception:
        return Response({"detail":"Categories are temporarily unavailable."},status=503)

@api_view(["GET", "POST", "PATCH", "DELETE"])
def manage_category(request):
    user, prof, error = _role_user(request, {"admin"})
    if error:
        return error
    data = request.data
    category_id = str(data.get("id") or data.get("category_id") or request.query_params.get("id") or "").strip()

    if request.method == "GET":
        try:
            with connection.cursor() as c:
                c.execute("""
                    select c.id,c.name,c.slug,c.image_url,c.sort_order,c.is_active,c.parent_id,
                           p.name as parent_name
                    from public.categories c
                    left join public.categories p on p.id=c.parent_id
                    order by coalesce(p.sort_order,c.sort_order),p.name,c.sort_order,c.name
                """)
                return Response(_rows(c))
        except Exception:
            return Response({"detail": "Categories could not be loaded."}, status=503)

    if request.method in {"PATCH", "DELETE"}:
        try:
            uuid.UUID(category_id)
        except (ValueError, TypeError, AttributeError):
            return Response({"detail": "Choose a valid category."}, status=400)
        if request.method == "DELETE":
            # Soft-delete categories to preserve historical product references.
            try:
                with connection.cursor() as c:
                    c.execute("update public.categories set is_active=false where id=%s returning id,name,is_active", [category_id])
                    row = c.fetchone()
                if not row:
                    return Response({"detail": "Category not found."}, status=404)
                cache.delete("catalog:categories:v3")
                return Response({"id": str(row[0]), "name": row[1], "is_active": row[2]})
            except Exception:
                return Response({"detail": "Category could not be deactivated."}, status=503)

    name = str(data.get("name", "")).strip()[:255] if "name" in data else ""
    image_url = str(data.get("image_url", "")).strip()[:1000]
    if image_url and not image_url.startswith("https://res.cloudinary.com/"):
        return Response({"detail": "Upload a category image through Cloudinary first."}, status=400)
    try:
        sort_order = int(data.get("sort_order", 0))
    except (TypeError, ValueError):
        return Response({"detail": "Sort order must be a whole number."}, status=400)

    try:
        with connection.cursor() as c:
            if request.method == "POST":
                if not name:
                    return Response({"detail": "Category name is required."}, status=400)
                base_slug = slugify(str(data.get("slug") or name))[:255].strip("-")
                if not base_slug:
                    return Response({"detail": "Enter a valid category name."}, status=400)
                slug = base_slug
                suffix = 2
                while True:
                    c.execute("select 1 from public.categories where slug=%s", [slug])
                    if not c.fetchone():
                        break
                    slug = f"{base_slug[:245]}-{suffix}"
                    suffix += 1
                parent_id = str(data.get("parent_id") or "").strip() or None
                if parent_id:
                    try:
                        uuid.UUID(parent_id)
                    except (ValueError, TypeError, AttributeError):
                        return Response({"detail": "Choose a valid parent category."}, status=400)
                    c.execute("select id from public.categories where id=%s and is_active=true", [parent_id])
                    if not c.fetchone():
                        return Response({"detail": "The selected parent category is unavailable."}, status=400)
                c.execute(
                    "insert into public.categories(name,slug,image_url,sort_order,is_active,parent_id) values(%s,%s,%s,%s,true,%s) returning id,name,slug,image_url,sort_order,is_active,parent_id",
                    [name, slug, image_url, sort_order, parent_id],
                )
            else:
                try:
                    uuid.UUID(category_id)
                except (ValueError, TypeError, AttributeError):
                    return Response({"detail": "Choose a valid category."}, status=400)
                fields = []
                params = []
                if "name" in data:
                    if not name:
                        return Response({"detail": "Category name is required."}, status=400)
                    fields.extend(["name=%s", "slug=%s"])
                    params.extend([name, slugify(str(data.get("slug") or name))[:255].strip("-")])
                if "image_url" in data:
                    fields.append("image_url=%s"); params.append(image_url)
                if "sort_order" in data:
                    fields.append("sort_order=%s"); params.append(sort_order)
                if "parent_id" in data:
                    parent_id = str(data.get("parent_id") or "").strip() or None
                    if parent_id == category_id:
                        return Response({"detail": "A category cannot be its own parent."}, status=400)
                    if parent_id:
                        try:
                            uuid.UUID(parent_id)
                        except (ValueError, TypeError, AttributeError):
                            return Response({"detail": "Choose a valid parent category."}, status=400)
                        c.execute("""
                            with recursive descendants(id) as (
                                select id from public.categories where parent_id=%s
                                union all
                                select child.id from public.categories child join descendants d on child.parent_id=d.id
                            ) select 1 from descendants where id=%s limit 1
                        """, [category_id, parent_id])
                        if c.fetchone():
                            return Response({"detail": "A category cannot be moved under one of its descendants."}, status=400)
                        c.execute("select id from public.categories where id=%s and is_active=true", [parent_id])
                        if not c.fetchone():
                            return Response({"detail": "The selected parent category is unavailable."}, status=400)
                    fields.append("parent_id=%s"); params.append(parent_id)
                if "is_active" in data:
                    if not isinstance(data["is_active"], bool):
                        return Response({"detail": "is_active must be true or false."}, status=400)
                    fields.append("is_active=%s"); params.append(data["is_active"])
                if not fields:
                    return Response({"detail": "Provide category fields to update."}, status=400)
                params.append(category_id)
                c.execute(
                    f"update public.categories set {', '.join(fields)} where id=%s returning id,name,slug,image_url,sort_order,is_active,parent_id",
                    params,
                )
            row = c.fetchone()
        if not row:
            return Response({"detail": "Category not found."}, status=404)
        result = {"id": str(row[0]), "name": row[1], "slug": row[2], "image_url": row[3], "sort_order": row[4], "is_active": row[5]}
        if len(row) > 6:
            result["parent_id"] = str(row[6]) if row[6] else None
        cache.delete("catalog:categories:v3")
        return Response(result, status=201 if request.method == "POST" else 200)
    except Exception:
        return Response({"detail": "Category could not be saved. Check for duplicate category names or slugs and retry."}, status=503)


@api_view(["GET", "POST", "PATCH", "DELETE"])
def manage_vendors(request):
    user, prof, error = _role_user(request, {"admin"})
    if error:
        return error
    if request.method == "GET":
        try:
            with connection.cursor() as c:
                c.execute(
                    """select v.id,v.owner_id,v.name,v.slug,v.description,v.logo_url,v.phone,v.address,
                              v.latitude,v.longitude,v.status,v.created_at,p.full_name as owner_name,p.phone as owner_phone,
                              u.email as owner_email
                       from public.vendors v
                       left join public.profiles p on p.id=v.owner_id
                       left join auth.users u on u.id=v.owner_id
                       order by case v.status when 'pending' then 0 when 'approved' then 1 else 2 end, v.created_at desc
                       limit 500"""
                )
                return Response({"results": _rows(c)})
        except Exception:
            return Response({"detail": "Vendor list could not be loaded."}, status=503)

    if request.method == "POST":
        data = request.data
        owner_user_id = str(data.get("owner_user_id") or "").strip()
        try:
            owner_user_id = str(uuid.UUID(owner_user_id))
        except (ValueError, TypeError, AttributeError):
            return Response({"detail": "Search for and select a valid existing website user."}, status=400)
        name = str(data.get("name", "")).strip()[:180]
        if not name:
            return Response({"detail": "Store/vendor name is required."}, status=400)
        phone = str(data.get("phone", "")).strip()[:30]
        address = str(data.get("address", "")).strip()[:500]
        description = str(data.get("description", "")).strip()[:2000]
        requested_status = str(data.get("status", "pending")).strip().lower()
        if requested_status not in {"pending", "approved", "rejected", "suspended"}:
            return Response({"detail": "Status must be pending, approved, rejected or suspended."}, status=400)
        try:
            latitude = _coordinate(data.get("latitude"), "latitude")
            longitude = _coordinate(data.get("longitude"), "longitude")
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        base_slug = slugify(name)[:240].strip("-")
        if not base_slug:
            return Response({"detail": "Enter a valid vendor/store name."}, status=400)
        try:
            with transaction.atomic():
                with connection.cursor() as c:
                    # Resolve the selected UUID against Supabase Auth and verify the account exists.
                    c.execute("select id, email, coalesce(raw_user_meta_data->>'full_name','') from auth.users where id=%s limit 1", [owner_user_id])
                    auth_user = c.fetchone()
                    if not auth_user:
                        return Response({"detail": "No website account exists for this UUID. The owner must register/sign in first."}, status=404)
                    owner_uuid = auth_user[0]
                    c.execute("select role from public.profiles where id=%s", [str(owner_uuid)])
                    existing_profile = c.fetchone()
                    if existing_profile and existing_profile[0] in {"admin", "delivery_boy"}:
                        return Response({"detail": "This account has an admin or delivery role. Select a separate customer account that matches the vendor email."}, status=400)
                    c.execute("select id from public.vendors where owner_id=%s limit 1", [str(owner_uuid)])
                    if c.fetchone():
                        return Response({"detail": "This Supabase account already owns a vendor. Each vendor must use a separate owner account."}, status=400)
                    c.execute(
                        """insert into public.profiles(id,full_name,phone,role)
                           values(%s,%s,%s,'vendor')
                           on conflict(id) do update set
                             full_name=case when excluded.full_name<>'' then excluded.full_name else public.profiles.full_name end,
                             phone=case when excluded.phone<>'' then excluded.phone else public.profiles.phone end,
                             role='vendor',
                             updated_at=now()""",
                        [str(owner_uuid), str(auth_user[2] or "")[:120], phone],
                    )
                    slug = base_slug
                    suffix = 2
                    while True:
                        c.execute("select 1 from public.vendors where slug=%s", [slug])
                        if not c.fetchone():
                            break
                        slug = f"{base_slug[:245]}-{suffix}"
                        suffix += 1
                    c.execute(
                        """insert into public.vendors(owner_id,name,slug,description,phone,address,latitude,longitude,status)
                           values(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           returning id,owner_id,name,slug,description,logo_url,phone,address,latitude,longitude,status,created_at""",
                        [str(owner_uuid), name, slug, description, phone, address, latitude, longitude, requested_status],
                    )
                    row = c.fetchone()
            result = {key: value for key, value in zip(
                ["id","owner_id","name","slug","description","logo_url","phone","address","latitude","longitude","status","created_at"], row
            )}
            result["id"] = str(result["id"])
            result["owner_id"] = str(result["owner_id"])
            result["vendor_id"] = result["id"]
            result["owner_user_id"] = result["owner_id"]
            if hasattr(result["created_at"], "isoformat"):
                result["created_at"] = result["created_at"].isoformat()
            return Response(result, status=201)
        except Exception:
            return Response({"detail": "Vendor could not be created. Confirm the selected user exists in Supabase Auth and that the database schema is up to date."}, status=503)

    vendor_id = str(request.data.get("id") or request.query_params.get("id") or "").strip()
    try:
        uuid.UUID(vendor_id)
    except (ValueError, TypeError, AttributeError):
        return Response({"detail": "Choose a valid vendor."}, status=400)
    if request.method == "DELETE":
        try:
            with transaction.atomic():
                with connection.cursor() as c:
                    c.execute("select id, owner_id, name from public.vendors where id=%s for update", [vendor_id])
                    vendor = c.fetchone()
                    if not vendor:
                        return Response({"detail": "Vendor not found."}, status=404)
                    c.execute("select 1 from public.orders where vendor_id=%s limit 1", [vendor_id])
                    if c.fetchone():
                        return Response({"detail": "This vendor has order history and cannot be permanently deleted. Set its status to suspended instead."}, status=409)
                    c.execute("delete from public.products where vendor_id=%s", [vendor_id])
                    c.execute("delete from public.vendors where id=%s", [vendor_id])
                    c.execute("update public.profiles set role='customer', updated_at=now() where id=%s and role='vendor'", [str(vendor[1])])
            return Response({"id": str(vendor[0]), "name": vendor[2], "deleted": True})
        except Exception:
            return Response({"detail": "Vendor could not be deleted. Suspend the vendor if it has dependent records."}, status=503)
    status_value = str(request.data.get("status", "")).strip().lower() if "status" in request.data else None
    if status_value is not None and status_value not in {"pending", "approved", "rejected", "suspended"}:
        return Response({"detail": "Status must be pending, approved, rejected or suspended."}, status=400)
    updates = []
    params = []
    if status_value is not None:
        updates.append("status=%s"); params.append(status_value)
    if "latitude" in request.data or "longitude" in request.data:
        try:
            latitude = _coordinate(request.data.get("latitude"), "latitude")
            longitude = _coordinate(request.data.get("longitude"), "longitude")
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        updates.extend(["latitude=%s", "longitude=%s"]); params.extend([latitude, longitude])
    if "address" in request.data:
        updates.append("address=%s"); params.append(str(request.data.get("address") or "").strip()[:500])
    if not updates:
        return Response({"detail": "Provide a vendor status, address or map location to update."}, status=400)
    params.append(vendor_id)
    try:
        with connection.cursor() as c:
            c.execute(
                f"update public.vendors set {', '.join(updates)} where id=%s returning id,name,slug,status,owner_id,latitude,longitude,address",
                params,
            )
            row = c.fetchone()
        if not row:
            return Response({"detail": "Vendor not found."}, status=404)
        return Response({"id": str(row[0]), "name": row[1], "slug": row[2], "status": row[3], "owner_id": str(row[4]) if row[4] else None, "latitude": row[5], "longitude": row[6], "address": row[7]})
    except Exception:
        return Response({"detail": "Vendor could not be updated. Confirm the delivery-location database migration has been applied."}, status=503)

@api_view(["GET"])
def products(request):
    """Bounded public catalog query with offset pagination and short-lived caching."""
    search = request.query_params.get("search", "").strip()[:100]
    category = request.query_params.get("category", "").strip()[:80]
    raw_limit = request.query_params.get("limit", "30")
    raw_offset = request.query_params.get("offset", "0")
    limit = min(max(int(raw_limit), 1), 60) if raw_limit.isdigit() else 30
    offset = min(max(int(raw_offset), 0), 1_000_000) if raw_offset.isdigit() else 0
    cache_fingerprint = hashlib.sha256(
        f"{search.lower()}|{category.lower()}|{limit}|{offset}".encode("utf-8")
    ).hexdigest()[:32]
    cache_key = f"catalog:products:v1:{cache_fingerprint}"
    cached = cache.get(cache_key)
    if cached is not None:
        return Response(cached)

    where = ["p.is_active=true", "v.status='approved'"]
    params = []
    if search:
        where.append("(p.name ilike %s or p.description ilike %s or v.name ilike %s)")
        params += [f"%{search}%"] * 3
    if category:
        # Selecting a parent category includes all of its descendants; selecting a
        # subcategory naturally restricts results to that subcategory and its children.
        where.append("""p.category_id in (
            with recursive category_tree(id) as (
                select id from public.categories where slug=%s and is_active=true
                union all
                select child.id from public.categories child join category_tree parent on child.parent_id=parent.id
                where child.is_active=true
            ) select id from category_tree
        )""")
        params.append(category)
    params.extend([limit + 1, offset])
    try:
        with connection.cursor() as c:
            c.execute(
                f"""select p.id,p.name,p.slug,p.description,p.price,p.compare_at_price,
                           p.image_url,p.image_public_id,p.sizes,p.colors,p.stock_quantity,p.size_prices,
                           p.category_id,c.name as category_name,c.slug as category_slug,
                           p.vendor_id,v.slug as vendor_slug
                    from public.products p
                    join public.vendors v on v.id=p.vendor_id
                    left join public.categories c on c.id=p.category_id
                    where {' and '.join(where)}
                    order by p.created_at desc,p.id desc
                    limit %s offset %s""",
                params,
            )
            rows = _rows(c)
        has_more = len(rows) > limit
        rows = rows[:limit]
        payload = {
            "results": rows,
            "count": len(rows),
            "has_more": has_more,
            "next_offset": offset + len(rows) if has_more else None,
        }
        # Checkout revalidates inventory; this short TTL limits stale catalog data.
        cache.set(cache_key, payload, 15)
        return Response(payload)
    except Exception:
        return Response({"detail":"Products are unavailable. Check the backend database connection."},status=503)



@api_view(["GET"])
def product_detail(request, product_id):
    """Public full product details, including the ordered Cloudinary image gallery."""
    try:
        with connection.cursor() as c:
            c.execute(
                """select p.id,p.name,p.slug,p.description,p.additional_description,
                          p.price,p.compare_at_price,p.image_url,p.image_public_id,
                          p.sizes,p.colors,p.stock_quantity,p.size_prices,p.category_id,
                          cat.name as category_name,cat.slug as category_slug,
                          p.vendor_id,v.slug as vendor_slug,
                          coalesce((
                            select json_agg(json_build_object(
                              'id',pi.id,'image_url',pi.image_url,
                              'image_public_id',pi.image_public_id,
                              'alt_text',pi.alt_text,'sort_order',pi.sort_order
                            ) order by pi.sort_order,pi.created_at)
                            from public.product_images pi where pi.product_id=p.id
                          ), '[]'::json) as gallery_images
                   from public.products p
                   join public.vendors v on v.id=p.vendor_id
                   left join public.categories cat on cat.id=p.category_id
                   where p.id=%s and p.is_active=true and v.status='approved'
                   limit 1""",
                [str(product_id)],
            )
            rows = _rows(c)
        if not rows:
            return Response({"detail": "This product is unavailable."}, status=404)
        return Response(rows[0])
    except Exception:
        logging.exception("Could not load full product details")
        return Response({"detail": "Product details are temporarily unavailable."}, status=503)

@api_view(["GET","PATCH"])
def profile(request):
    user,error=_user(request)
    if error:return error
    try:
        if request.method=="PATCH":
            name=str(request.data.get("full_name",""))[:120];phone=str(request.data.get("phone",""))[:30]
            with connection.cursor() as c:
                c.execute("""insert into public.profiles(id,full_name,phone,role) values(%s,%s,%s,'customer') on conflict(id) do update set full_name=excluded.full_name,phone=excluded.phone,updated_at=now() returning id,full_name,phone,role""",[user["id"],name,phone])
                row=c.fetchone()
            return Response({"id":str(row[0]),"full_name":row[1],"phone":row[2],"role":row[3]})
        return Response(_profile(user["id"]))
    except Exception:return Response({"detail":"Profile is unavailable."},status=503)

@api_view(["POST"])
def delivery_quote(request):
    """Return an OSRM quote measured from Rayachoti Bus Stand for an approved vendor's products."""
    user, error = _user(request)
    if error:
        return error
    vendor_id = str(request.data.get("vendor_id", "")).strip()
    try:
        uuid.UUID(vendor_id)
        customer_latitude = _coordinate(request.data.get("latitude"), "latitude")
        customer_longitude = _coordinate(request.data.get("longitude"), "longitude")
    except (ValueError, TypeError, AttributeError) as exc:
        return Response({"detail": str(exc) or "Choose a valid vendor and customer map location."}, status=400)
    try:
        with connection.cursor() as c:
            c.execute(
                "select name from public.vendors where id=%s and status='approved'",
                [vendor_id],
            )
            vendor = c.fetchone()
        if not vendor:
            return Response({"detail": "This vendor is not available for delivery."}, status=404)
        distance_meters = road_distance_meters(
            RAYACHOTI_BUS_STAND_LATITUDE,
            RAYACHOTI_BUS_STAND_LONGITUDE,
            customer_latitude,
            customer_longitude,
        )
        if distance_meters > MAX_DELIVERY_DISTANCE_METERS:
            return Response({
                "detail": f"This address is outside the 5 km road-delivery area from Rayachoti Bus Stand ({distance_meters / 1000:.2f} km by road). Choose a nearer location."
            }, status=400)
        return Response({
            "vendor_id": vendor_id,
            "vendor_name": vendor[0],
            "delivery_origin": "Rayachoti Bus Stand",
            "distance_meters": int(round(distance_meters)),
            "distance_km": round(distance_meters / 1000, 2),
            "delivery_fee": str(delivery_fee_for_distance(distance_meters)),
            "max_distance_km": MAX_DELIVERY_DISTANCE_METERS / 1000,
            "fee_per_500m": str(DELIVERY_BLOCK_FEE),
        })
    except RuntimeError as exc:
        return Response({"detail": str(exc)}, status=503)
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=400)
    except Exception:
        return Response({"detail": "Could not calculate the delivery quote. Please retry."}, status=503)


@api_view(["GET","POST"])
def orders(request):
    user,error=_user(request)
    if error:return error
    if request.method=="GET":
        try:
            with connection.cursor() as c:
                c.execute("""select o.id,o.order_number,o.status,o.payment_method,o.payment_status,o.subtotal,o.delivery_fee,o.total,o.created_at,o.address_snapshot,o.notes,o.vendor_name_snapshot as vendor_name,o.vendor_address_snapshot as vendor_address,o.vendor_phone_snapshot as vendor_phone,o.vendor_latitude_snapshot as vendor_latitude,o.vendor_longitude_snapshot as vendor_longitude,case when o.status in ('out_for_delivery','delivered') then dp.full_name else null end as delivery_person_name,case when o.status in ('out_for_delivery','delivered') then dp.phone else null end as delivery_person_phone,coalesce(json_agg(json_build_object('product_id',oi.product_id,'product_name',oi.product_name,'image_url',oi.image_url,'quantity',oi.quantity,'size',oi.size,'color',oi.color,'unit_price',oi.unit_price,'line_total',oi.line_total)) filter(where oi.id is not null),'[]'::json) as items from public.orders o left join public.order_items oi on oi.order_id=o.id left join public.profiles dp on dp.id=o.assigned_delivery_boy_id where o.customer_id=%s group by o.id,dp.full_name,dp.phone order by o.created_at desc limit 50""",[user["id"]])
                rows=_rows(c)
            return Response({"results":rows,"count":len(rows)})
        except Exception:return Response({"detail":"Order history is unavailable."},status=503)
    data=request.data
    submitted_address=data.get("address") if isinstance(data.get("address"),dict) else {}
    items=data.get("items")
    if not isinstance(items,list) or not 1<=len(items)<=30:
        return Response({"detail":"Provide 1–30 cart items."},status=400)

    # Resolve the selected/default saved address on the server. Never trust
    # address fields sent by the browser: the order receives a checkout-time snapshot.
    requested_address_id = submitted_address.get("saved_address_id") or submitted_address.get("id") or ""
    # Older clients may submit editable address fields without a saved-address ID.
    # Reject those requests rather than silently substituting a different default address.
    if not requested_address_id and submitted_address:
        return Response({
            "detail": "Refresh the storefront and choose a saved delivery address before placing this order."
        }, status=409)
    try:
        with transaction.atomic():
            with connection.cursor() as c:
                try:
                    address = _resolve_order_address(c, user["id"], requested_address_id)
                except ValueError as exc:
                    return Response({"detail": str(exc)}, status=400)

            address_issues = _order_address_issues(address)
            if address_issues:
                return Response({
                    "detail": "Saved delivery address is incomplete or invalid. Update it before placing the order: " + ", ".join(address_issues) + "."
                }, status=400)
            recipient = str(address.get("recipient_name", "")).strip()[:120]
            phone = str(address.get("phone", "")).strip()[:30]
            line1 = str(address.get("line1", "")).strip()[:200]
            customer_latitude = _coordinate(address.get("latitude"), "latitude")
            customer_longitude = _coordinate(address.get("longitude"), "longitude")
            snapshot = {
                "saved_address_id": address["id"],
                "recipient_name": recipient,
                "phone": phone,
                "line1": line1,
                "line2": str(address.get("line2", ""))[:200],
                "landmark": str(address.get("landmark", ""))[:160],
                "city": "Rayachoty",
                "state": "Andhra Pradesh",
                "postal_code": str(address.get("postal_code", ""))[:20],
                "latitude": customer_latitude,
                "longitude": customer_longitude,
            }
            vendor=None;subtotal=Decimal("0.00");verified=[];seen=set()
            for raw in items:
                pid=str(raw.get("product_id",""))
                try:uuid.UUID(pid);qty=int(raw.get("quantity",0))
                except (ValueError,TypeError,AttributeError):return Response({"detail":"Cart has invalid product ID or quantity."},status=400)
                if not 1<=qty<=20:return Response({"detail":"Each quantity must be between 1 and 20."},status=400)
                if pid in seen:return Response({"detail":"Combine duplicate cart lines before checkout."},status=400)
                seen.add(pid)
                with connection.cursor() as c:
                    c.execute("""select p.id,p.name,p.price,p.image_url,p.stock_quantity,p.sizes,p.colors,p.vendor_id,p.sku,p.size_prices from public.products p join public.vendors v on v.id=p.vendor_id where p.id=%s and p.is_active=true and v.status='approved' for update of p""",[pid])
                    row=c.fetchone()
                if not row:return Response({"detail":"A product is no longer available."},status=409)
                prod_id,name,price,image,stock,sizes,colors,vendor_id,sku,size_prices=row
                if stock<qty:return Response({"detail":f"Only {stock} left for {name}."},status=409)
                if vendor is None:vendor=vendor_id
                elif vendor!=vendor_id:return Response({"detail":"Please check out one seller at a time."},status=400)
                size=str(raw.get("size",""))[:30];color=str(raw.get("color",""))[:50]
                if size_prices and size in size_prices:
                    try: price=Decimal(str(size_prices[size]))
                    except (InvalidOperation,TypeError,ValueError): return Response({"detail":f"Invalid configured price for size {size}."},status=409)
                    if not price.is_finite() or price < 0: return Response({"detail":f"Invalid configured price for size {size}."},status=409)
                if sizes and size and size not in sizes:return Response({"detail":f"Size is unavailable for {name}."},status=409)
                if colors and color and color not in colors:return Response({"detail":f"Colour is unavailable for {name}."},status=409)
                line=(price*qty).quantize(Decimal("0.01"));subtotal+=line
                verified.append({"id":prod_id,"name":name,"price":price,"image":image or "","qty":qty,"size":size,"color":color,"line":line})
            if subtotal < Decimal("250.00"):
                return Response({"detail":"Minimum order amount is ₹250. Add more items to continue."},status=400)
            try:
                distance_meters = road_distance_meters(
                    RAYACHOTI_BUS_STAND_LATITUDE,
                    RAYACHOTI_BUS_STAND_LONGITUDE,
                    customer_latitude,
                    customer_longitude,
                )
            except RuntimeError as exc:
                return Response({"detail": str(exc)}, status=503)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=400)
            if distance_meters > MAX_DELIVERY_DISTANCE_METERS:
                return Response({"detail": f"Sorry, this order is outside the 5 km road-delivery area from Rayachoti Bus Stand ({distance_meters / 1000:.2f} km by road). Choose a nearer delivery location."}, status=400)
            fee = delivery_fee_for_distance(distance_meters)
            snapshot["delivery_distance_meters"] = int(round(distance_meters))
            total=subtotal+fee;number="BFR-"+uuid.uuid4().hex[:10].upper()
            with connection.cursor() as c:
                c.execute("""select id,name,phone,address,latitude,longitude,owner_id
                             from public.vendors where id=%s and status='approved' for share""", [str(vendor)])
                vendor_row = c.fetchone()
                if not vendor_row:
                    return Response({"detail": "The seller is no longer available for checkout."}, status=409)
                vendor_snapshot = {
                    "vendor_name": str(vendor_row[1] or "").strip(),
                    "vendor_phone": str(vendor_row[2] or "").strip(),
                    "vendor_address": str(vendor_row[3] or "").strip(),
                    "vendor_latitude": vendor_row[4],
                    "vendor_longitude": vendor_row[5],
                }
                if not vendor_snapshot["vendor_name"] or not vendor_snapshot["vendor_phone"] or not vendor_snapshot["vendor_address"]:
                    return Response({"detail": "The seller's contact and pickup address are incomplete. Contact support before ordering."}, status=409)
                try:
                    vendor_snapshot["vendor_latitude"] = _coordinate(vendor_snapshot["vendor_latitude"], "latitude")
                    vendor_snapshot["vendor_longitude"] = _coordinate(vendor_snapshot["vendor_longitude"], "longitude")
                except ValueError:
                    return Response({"detail": "The seller's pickup map location is incomplete. Contact support before ordering."}, status=409)
                c.execute("""insert into public.orders(
                    order_number,customer_id,vendor_id,status,payment_method,payment_status,
                    subtotal,delivery_fee,total,address_snapshot,notes,
                    vendor_name_snapshot,vendor_phone_snapshot,vendor_address_snapshot,
                    vendor_latitude_snapshot,vendor_longitude_snapshot
                ) values(%s,%s,%s,'placed','cod','pending',%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s)
                returning id,order_number,status,payment_method,subtotal,delivery_fee,total,created_at""",
                [number,user["id"],vendor,subtotal,fee,total,json.dumps(snapshot),
                 str(data.get("notes",""))[:500],vendor_snapshot["vendor_name"],
                 vendor_snapshot["vendor_phone"],vendor_snapshot["vendor_address"],
                 vendor_snapshot["vendor_latitude"],vendor_snapshot["vendor_longitude"]])
                order=c.fetchone();order_id=order[0]
                for i in verified:
                    c.execute("update public.products set stock_quantity=stock_quantity-%s,updated_at=now() where id=%s and stock_quantity >= %s",[i["qty"],i["id"],i["qty"]])
                    if c.rowcount!=1:raise ValueError("Inventory changed during checkout. Please retry.")
                    c.execute("""insert into public.order_items(order_id,product_id,product_name,image_url,size,color,quantity,unit_price,line_total) values(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",[order_id,i["id"],i["name"],i["image"],i["size"],i["color"],i["qty"],i["price"],i["line"]])

                # Only the two requested events are persisted: placed and delivered.
                if vendor_row and vendor_row[6]:
                    _insert_account_notification(
                        c, vendor_row[6], "placed", "New order placed",
                        f"Order {order[1]} has been placed.", order_id,
                    )
                _notify_admins(
                    c, "placed", "New order placed",
                    f"Order {order[1]} has been placed.", order_id,
                )
            return Response({"id":str(order[0]),"order_number":order[1],"status":order[2],"payment_method":order[3],"subtotal":str(order[4]),"delivery_fee":str(order[5]),"total":str(order[6]),"created_at":order[7].isoformat(),"address_snapshot":snapshot,"vendor_snapshot":vendor_snapshot,"notes":str(data.get("notes",""))[:500]},status=201)
    except ValueError as e:return Response({"detail":str(e)},status=409)
    except Exception:return Response({"detail":"Could not place order. Please retry or contact support."},status=503)


@api_view(["GET", "PATCH", "DELETE"])
def manage_orders(request):
    """Admins manage accounts/assignments and may delete orders; vendors and assigned delivery staff process orders."""
    user, prof, error = _role_user(request, {"vendor", "admin"})
    if error:
        return error

    # Order deletion is an explicit admin-only maintenance action. Vendors and
    # delivery staff cannot delete records; processing permissions remain separate.
    if request.method == "DELETE":
        if prof["role"] != "admin":
            return Response({"detail": "Only an administrator can delete an order."}, status=403)
        order_id = str(request.data.get("id") or request.data.get("order_id") or request.query_params.get("id") or "").strip()
        try:
            uuid.UUID(order_id)
        except (ValueError, TypeError, AttributeError):
            return Response({"detail": "Choose a valid order."}, status=400)
        try:
            with transaction.atomic():
                with connection.cursor() as c:
                    c.execute(
                        "delete from public.orders where id=%s returning id,order_number",
                        [order_id],
                    )
                    deleted = c.fetchone()
            if not deleted:
                return Response({"detail": "Order not found."}, status=404)
            return Response({"id": str(deleted[0]), "order_number": deleted[1], "deleted": True})
        except Exception:
            return Response({"detail": "Order could not be deleted. Check dependent records and database constraints."}, status=409)

    if request.method == "PATCH":
        if prof["role"] != "vendor":
            return Response({"detail": "Only the vendor who owns this order can confirm, reject, or pack it. Delivery status is handled by the assigned delivery person."}, status=403)
        order_id = str(request.data.get("id") or request.data.get("order_id") or request.query_params.get("id") or "").strip()
        try:
            uuid.UUID(order_id)
        except (ValueError, TypeError, AttributeError):
            return Response({"detail": "Choose a valid order."}, status=400)

        status_value = str(request.data.get("status") or "").strip().lower()
        allowed_statuses = {"placed", "confirmed", "packed", "out_for_delivery", "delivered", "cancelled"}
        if status_value not in allowed_statuses:
            return Response({"detail": "Choose a valid order status."}, status=400)

        try:
            with transaction.atomic():
                with connection.cursor() as c:
                    if prof["role"] == "vendor":
                        c.execute(
                            """select o.id, o.status, o.payment_method, o.payment_status, o.customer_id, o.order_number
                               from public.orders o
                               join public.vendors v on v.id=o.vendor_id
                               where o.id=%s and v.owner_id=%s and v.status='approved'
                               for update of o""",
                            [order_id, user["id"]],
                        )
                    current = c.fetchone()
                    if not current:
                        return Response({"detail": "Order not found or you do not have permission to manage it."}, status=404)

                    current_status = current[1]
                    transitions = {
                        "placed": {"confirmed", "cancelled"},
                        "confirmed": {"packed", "cancelled"},
                        "packed": set(),
                        "out_for_delivery": set(),
                        "delivered": set(),
                        "cancelled": set(),
                    }
                    if status_value != current_status and status_value not in transitions.get(current_status, set()):
                        return Response(
                            {"detail": f"Order cannot move from {current_status} to {status_value}."},
                            status=409,
                        )
                    c.execute(
                        """update public.orders
                           set status=%s,
                               payment_status=case
                                   when %s='delivered' and payment_method='cod' and payment_status='pending'
                                   then 'paid'
                                   else payment_status
                               end,
                               updated_at=now()
                           where id=%s
                           returning id, order_number, status, payment_status, total, created_at""",
                        [status_value, status_value, order_id],
                    )
                    row = c.fetchone()
                    if status_value == "delivered" and current_status != "delivered":
                        customer_id, order_number = current[4], current[5]
                        _insert_account_notification(
                            c, customer_id, "delivered", "Your order was delivered",
                            f"Order {order_number} has been delivered.", current[0],
                        )
                        _notify_admins(
                            c, "delivered", "Order delivered",
                            f"Order {order_number} has been delivered.", current[0],
                        )
            return Response({
                "id": str(row[0]), "order_number": row[1], "status": row[2],
                "payment_status": row[3], "total": str(row[4]),
                "created_at": row[5].isoformat() if hasattr(row[5], "isoformat") else row[5],
            })
        except Exception:
            return Response({"detail": "Order status could not be updated. Please retry."}, status=503)

    try:
        with connection.cursor() as c:
            if prof["role"] == "vendor":
                c.execute(
                    """select o.id,o.order_number,o.status,o.payment_method,o.payment_status,
                              o.subtotal,o.delivery_fee,o.total,
                              '{}'::jsonb as address_snapshot,
                              '' as notes,o.created_at,v.name as vendor_name,
                              coalesce(json_agg(json_build_object(
                                'product_name',oi.product_name,'image_url',oi.image_url,
                                'quantity',oi.quantity,'size',oi.size,'color',oi.color,
                                'line_total',oi.line_total
                              )) filter(where oi.id is not null),'[]'::json) as items
                       from public.orders o
                       join public.vendors v on v.id=o.vendor_id
                       left join public.order_items oi on oi.order_id=o.id
                       where v.owner_id=%s and v.status='approved'
                       group by o.id,v.name order by o.created_at desc limit 100""",
                    [user["id"]],
                )
            else:
                c.execute(
                    """select o.id,o.order_number,o.status,o.payment_method,o.payment_status,
                              o.subtotal,o.delivery_fee,o.total,
                              coalesce(o.address_snapshot, '{}'::jsonb) as address_snapshot,
                              o.notes,o.created_at,o.vendor_name_snapshot as vendor_name,o.vendor_address_snapshot as vendor_address,o.vendor_phone_snapshot as vendor_phone,
                              cu.email as customer_email,
                              dp.full_name as delivery_person_name,dp.phone as delivery_person_phone,
                              o.assigned_delivery_boy_id,
                              coalesce(json_agg(json_build_object(
                                'product_id',oi.product_id,'product_name',oi.product_name,'image_url',oi.image_url,
                                'quantity',oi.quantity,'size',oi.size,'color',oi.color,
                                'unit_price',oi.unit_price,'line_total',oi.line_total
                              )) filter(where oi.id is not null),'[]'::json) as items
                       from public.orders o
                       join public.vendors v on v.id=o.vendor_id
                       left join auth.users cu on cu.id=o.customer_id
                       left join public.profiles dp on dp.id=o.assigned_delivery_boy_id
                       left join public.order_items oi on oi.order_id=o.id
                       group by o.id,cu.email,dp.full_name,dp.phone
                       order by o.created_at desc limit 200"""
                )
            rows = _rows(c)
        return Response({"results": rows, "count": len(rows), "role": prof["role"]})
    except Exception:
        return Response({"detail": "Orders could not be loaded. Check the backend database connection."}, status=503)


@api_view(["GET", "PATCH"])
def account_notifications(request):
    """Read and mark read only notifications belonging to the authenticated Supabase account."""
    user, error = _user(request)
    if error:
        return error

    try:
        with connection.cursor() as c:
            if request.method == "PATCH":
                notification_id = str(request.data.get("id") or "").strip()
                if request.data.get("mark_all_read") is True:
                    c.execute(
                        """update public.account_notifications set read_at=now()
                           where recipient_id=%s and read_at is null""",
                        [user["id"]],
                    )
                else:
                    try:
                        uuid.UUID(notification_id)
                    except (ValueError, TypeError, AttributeError):
                        return Response({"detail": "Choose a valid notification or mark all as read."}, status=400)
                    c.execute(
                        """update public.account_notifications set read_at=now()
                           where id=%s and recipient_id=%s and read_at is null""",
                        [notification_id, user["id"]],
                    )
                    if c.rowcount == 0:
                        c.execute(
                            "select 1 from public.account_notifications where id=%s and recipient_id=%s",
                            [notification_id, user["id"]],
                        )
                        if not c.fetchone():
                            return Response({"detail": "Notification not found."}, status=404)

            c.execute(
                """select id,event_type,title,body,order_id,created_at,read_at
                   from public.account_notifications
                   where recipient_id=%s
                   order by created_at desc limit 100""",
                [user["id"]],
            )
            rows = _rows(c)
        return Response({"results": rows, "count": len(rows), "unread_count": sum(1 for item in rows if not item["read_at"])})
    except Exception:
        return Response({"detail": "Notifications are temporarily unavailable. Verify the account_notifications database table exists."}, status=503)


@api_view(["POST"])
def upload_signature(request):
    user,prof,error=_role_user(request,{"vendor","admin"})
    if error:return error
    if not all([CLOUD_NAME,CLOUD_KEY,CLOUD_SECRET]):return Response({"detail":"Cloudinary credentials are not configured on the backend."},status=503)
    folder=str(request.data.get("folder","bala-fashion/products"))[:100]
    if folder not in {"bala-fashion/products","bala-fashion/products/gallery","bala-fashion/categories"}:
        return Response({"detail":"Invalid upload folder."},status=400)
    if prof["role"] == "vendor" and folder not in {"bala-fashion/products","bala-fashion/products/gallery"}:
        return Response({"detail":"Sellers can upload product images only."},status=403)
    import time
    params={"timestamp":int(time.time()),"folder":folder}
    return Response({"cloud_name":CLOUD_NAME,"api_key":CLOUD_KEY,"params":params,"signature":api_sign_request(params,CLOUD_SECRET)})

@api_view(["GET"])
def seller_dashboard(request):
    """Return only the stores and records the authenticated role is allowed to manage."""
    user, prof, error = _role_user(request, {"vendor", "admin"})
    if error:
        return error
    search = request.query_params.get("search", "").strip()[:100]
    category = request.query_params.get("category", "").strip()[:80]
    order_search = request.query_params.get("order_search", "").strip()[:100]
    raw_limit = request.query_params.get("limit", "30")
    raw_offset = request.query_params.get("offset", "0")
    raw_order_offset = request.query_params.get("order_offset", "0")
    limit = min(max(int(raw_limit), 1), 30) if raw_limit.isdigit() else 30
    offset = min(max(int(raw_offset), 0), 1_000_000) if raw_offset.isdigit() else 0
    order_offset = min(max(int(raw_order_offset), 0), 1_000_000) if raw_order_offset.isdigit() else 0
    try:
        with connection.cursor() as c:
            if prof["role"] == "vendor":
                c.execute("select id,name,slug,status,logo_url from public.vendors where owner_id=%s order by name", [user["id"]])
            else:
                c.execute("select id,name,slug,status,logo_url from public.vendors order by name")
            stores = _rows(c)
            if prof["role"] == "vendor":
                stores = [store for store in stores if store["status"] == "approved"]
            store_ids = [store["id"] for store in stores]
            if not store_ids:
                return Response({"role": prof["role"], "stores": [], "products": [], "product_count": 0,
                    "product_limit": limit, "product_offset": offset, "product_has_more": False,
                    "orders": [], "order_count": 0, "order_limit": limit, "order_offset": order_offset, "order_has_more": False,
                    "stats": {"products": 0, "active_products": 0, "low_stock": 0, "orders": 0}})
            product_where = ["p.vendor_id = any(%s)", "v.status='approved'"]
            product_params = [store_ids]
            if search:
                product_where.append("(p.name ilike %s or coalesce(v.name,'') ilike %s or coalesce(c.name,'') ilike %s or p.id::text ilike %s)")
                product_params.extend([f"%{search}%"] * 4)
            if category:
                product_where.append("""p.category_id in (
                    with recursive category_tree(id) as (
                        select id from public.categories where slug=%s
                        union all
                        select child.id from public.categories child join category_tree parent on child.parent_id=parent.id
                    ) select id from category_tree
                )""")
                product_params.append(category)
            where_sql = " and ".join(product_where)
            c.execute(f"""select count(*) as total,
                count(*) filter (where p.is_active) as active_total,
                count(*) filter (where coalesce(p.stock_quantity,0) <= 5) as low_stock_total
                from public.products p left join public.categories c on c.id=p.category_id
                join public.vendors v on v.id=p.vendor_id where {where_sql}""", product_params)
            product_totals = _rows(c)[0]
            product_count = int(product_totals["total"] or 0)
            c.execute(f"""select p.id,p.name,p.slug,p.description,p.price,p.compare_at_price,
                p.image_url,p.image_public_id,p.sizes,p.colors,p.stock_quantity,p.size_prices,
                p.additional_description,p.category_id,p.vendor_id,p.is_active,p.created_at,
                c.name as category_name,c.slug as category_slug,v.name as vendor_name,
                coalesce((select json_agg(json_build_object(
                    'id',pi.id,'image_url',pi.image_url,'image_public_id',pi.image_public_id,
                    'alt_text',pi.alt_text,'sort_order',pi.sort_order
                ) order by pi.sort_order,pi.created_at) from public.product_images pi
                    where pi.product_id=p.id), '[]'::json) as extra_images
                from public.products p left join public.categories c on c.id=p.category_id
                join public.vendors v on v.id=p.vendor_id where {where_sql}
                order by p.created_at desc,p.id desc limit %s offset %s""",
                product_params + [limit + 1, offset])
            managed_products = _rows(c)
            product_has_more = len(managed_products) > limit
            managed_products = managed_products[:limit]
            order_where = ["o.vendor_id = any(%s)"]
            order_params = [store_ids]
            if order_search:
                order_where.append("""(
                    o.order_number::text ilike %s or o.status ilike %s
                    or coalesce(o.payment_status,'') ilike %s
                    or coalesce(o.payment_method,'') ilike %s
                    or coalesce(o.vendor_name_snapshot,'') ilike %s
                    or coalesce(cu.email,'') ilike %s
                    or o.id::text ilike %s
                )""")
                order_params.extend([f"%{order_search}%"] * 7)
            order_where_sql = " and ".join(order_where)
            c.execute(f"""select count(*) as total
                from public.orders o
                left join auth.users cu on cu.id=o.customer_id
                where {order_where_sql}""", order_params)
            order_count = int(_rows(c)[0]["total"] or 0)
            c.execute(
                f"""select o.id,o.order_number,o.status,o.payment_status,o.total,o.created_at,
                          o.assigned_delivery_boy_id,o.vendor_name_snapshot as vendor_name,o.vendor_address_snapshot as vendor_address,o.vendor_phone_snapshot as vendor_phone,o.payment_method,o.subtotal,o.delivery_fee,
                          o.notes,
                          case when %s in ('admin','vendor') then jsonb_build_object(
                            'latitude',o.address_snapshot->>'latitude',
                            'longitude',o.address_snapshot->>'longitude'
                          ) else null end as delivery_coordinates,
                          case when %s in ('admin','vendor') then (
                            coalesce(o.address_snapshot, '{{}}'::jsonb)
                          ) else null end as address_snapshot,
                          cu.email as customer_email,
                          dp.full_name as delivery_person_name,dp.phone as delivery_person_phone,
                          coalesce(json_agg(json_build_object(
                            'product_id',oi.product_id,'product_name',oi.product_name,
                            'image_url',oi.image_url,'quantity',oi.quantity,'size',oi.size,
                            'color',oi.color,'unit_price',oi.unit_price,'line_total',oi.line_total
                          )) filter(where oi.id is not null),'[]'::json) as items
                   from public.orders o
                   join public.vendors v on v.id=o.vendor_id
                   left join auth.users cu on cu.id=o.customer_id
                   left join public.profiles dp on dp.id=o.assigned_delivery_boy_id
                   left join public.order_items oi on oi.order_id=o.id
                   where {order_where_sql}
                   group by o.id,v.name,v.address,v.phone,cu.email,dp.full_name,dp.phone
                   order by o.created_at desc,o.id desc limit %s offset %s""",
                [prof["role"], prof["role"]] + order_params + [limit + 1, order_offset],
            )
            managed_orders = _rows(c)
            order_has_more = len(managed_orders) > limit
            managed_orders = managed_orders[:limit]
        return Response({
            "role": prof["role"], "stores": stores, "products": managed_products,
            "product_count": product_count, "product_limit": limit, "product_offset": offset,
            "product_has_more": product_has_more,
            "orders": managed_orders, "order_count": order_count, "order_limit": limit,
            "order_offset": order_offset, "order_has_more": order_has_more,
            "stats": {
                "products": product_count,
                "active_products": int(product_totals["active_total"] or 0),
                "low_stock": int(product_totals["low_stock_total"] or 0),
                "orders": order_count,
            },
        })
    except Exception:
        return Response({"detail": "Seller dashboard data is temporarily unavailable."}, status=503)


@api_view(["GET", "POST", "PATCH", "DELETE"])
def manage_product(request):
    user, prof, error = _role_user(request, {"vendor", "admin"})
    if error:
        return error

    def allowed_store(vendor_id):
        with connection.cursor() as c:
            if prof["role"] == "vendor":
                c.execute(
                    "select id from public.vendors where id=%s and owner_id=%s and status='approved'",
                    [vendor_id, user["id"]],
                )
            else:
                c.execute(
                    "select id from public.vendors where id=%s and status='approved'",
                    [vendor_id],
                )
            return c.fetchone() is not None

    if request.method == "GET":
        try:
            with connection.cursor() as c:
                if prof["role"] == "vendor":
                    c.execute(
                        """select p.id,p.name,p.slug,p.description,p.price,p.compare_at_price,
                                  p.image_url,p.image_public_id,p.sizes,p.colors,p.stock_quantity,p.size_prices,
                                  p.additional_description,p.category_id,p.vendor_id,p.is_active,p.created_at,
                                  c.name as category_name,v.name as vendor_name,
                                  coalesce((select json_agg(json_build_object(
                                    'id',pi.id,'image_url',pi.image_url,'image_public_id',pi.image_public_id,
                                    'alt_text',pi.alt_text,'sort_order',pi.sort_order
                                  ) order by pi.sort_order,pi.created_at) from public.product_images pi
                                    where pi.product_id=p.id), '[]'::json) as extra_images
                           from public.products p
                           left join public.categories c on c.id=p.category_id
                           join public.vendors v on v.id=p.vendor_id
                           where v.owner_id=%s and v.status='approved'
                           order by p.created_at desc limit 200""",
                        [user["id"]],
                    )
                else:
                    c.execute(
                        """select p.id,p.name,p.slug,p.description,p.price,p.compare_at_price,
                                  p.image_url,p.image_public_id,p.sizes,p.colors,p.stock_quantity,p.size_prices,
                                  p.additional_description,p.category_id,p.vendor_id,p.is_active,p.created_at,
                                  c.name as category_name,v.name as vendor_name,
                                  coalesce((select json_agg(json_build_object(
                                    'id',pi.id,'image_url',pi.image_url,'image_public_id',pi.image_public_id,
                                    'alt_text',pi.alt_text,'sort_order',pi.sort_order
                                  ) order by pi.sort_order,pi.created_at) from public.product_images pi
                                    where pi.product_id=p.id), '[]'::json) as extra_images
                           from public.products p
                           left join public.categories c on c.id=p.category_id
                           join public.vendors v on v.id=p.vendor_id
                           order by p.created_at desc limit 200"""
                    )
                return Response({"results": _rows(c)})
        except Exception:
            return Response({"detail": "Managed products could not be loaded."}, status=503)

    data = request.data
    if request.method in {"PATCH", "DELETE"}:
        product_id = str(data.get("id") or request.query_params.get("id") or "").strip()
        try:
            uuid.UUID(product_id)
        except (ValueError, TypeError, AttributeError):
            return Response({"detail": "Choose a valid product."}, status=400)
        try:
            with connection.cursor() as c:
                if prof["role"] == "vendor":
                    c.execute(
                        """select p.id,p.vendor_id from public.products p
                           join public.vendors v on v.id=p.vendor_id
                           where p.id=%s and v.owner_id=%s and v.status='approved'""",
                        [product_id, user["id"]],
                    )
                else:
                    c.execute(
                        """select p.id,p.vendor_id from public.products p
                           join public.vendors v on v.id=p.vendor_id
                           where p.id=%s and v.status='approved'""",
                        [product_id],
                    )
                existing = c.fetchone()
            if not existing:
                return Response({"detail": "Product not found or you do not have permission to manage it."}, status=404)
            # Visibility-only PATCH requests must be handled before the full edit
            # validation below. Otherwise the Publish button fails with "Product
            # name is required" and hidden products cannot be republished.
            if request.method == "PATCH" and "is_active" in data and set(data.keys()).issubset({"id", "is_active"}):
                if not isinstance(data.get("is_active"), bool):
                    return Response({"detail": "Product visibility must be true or false."}, status=400)
                with connection.cursor() as c:
                    c.execute(
                        "update public.products set is_active=%s,updated_at=now() where id=%s returning id,name,is_active",
                        [data["is_active"], product_id],
                    )
                    row = c.fetchone()
                if not row:
                    return Response({"detail": "Product not found."}, status=404)
                return Response({
                    "id": str(row[0]), "name": row[1], "is_active": row[2],
                    "detail": "Product published." if row[2] else "Product unpublished.",
                })
            if request.method == "DELETE":
                with connection.cursor() as c:
                    c.execute(
                        "update public.products set is_active=false,updated_at=now() where id=%s returning id,name,is_active",
                        [product_id],
                    )
                    row = c.fetchone()
                return Response({"id": str(row[0]), "name": row[1], "is_active": row[2], "detail": "Product unpublished."})
            # A status-only PATCH lets an authorized owner/admin republish hidden items
            # without resubmitting product fields or changing inventory and pricing.
            if request.method == "PATCH" and "is_active" in data and set(data.keys()).issubset({"id", "is_active"}):
                is_active = data.get("is_active")
                if not isinstance(is_active, bool):
                    return Response({"detail": "is_active must be true or false."}, status=400)
                with connection.cursor() as c:
                    c.execute(
                        "update public.products set is_active=%s,updated_at=now() where id=%s returning id,name,is_active",
                        [is_active, product_id],
                    )
                    row = c.fetchone()
                return Response({
                    "id": str(row[0]), "name": row[1], "is_active": row[2],
                    "detail": "Product published." if row[2] else "Product unpublished.",
                })
        except Exception:
            return Response({"detail": "Product could not be updated. Please retry."}, status=503)

    name = str(data.get("name", "")).strip()[:180]
    if not name:
        return Response({"detail": "Product name is required."}, status=400)
    try:
        price = Decimal(str(data.get("price", "")))
        compare_raw = data.get("compare_at_price")
        compare_price = Decimal(str(compare_raw)) if compare_raw not in (None, "") else None
        stock = int(data.get("stock_quantity", 0))
        if not price.is_finite() or price < 0 or stock < 0:
            raise ValueError()
        if compare_price is not None and (not compare_price.is_finite() or compare_price < price):
            return Response({"detail": "Compare price must be greater than or equal to the selling price."}, status=400)
    except (ValueError, InvalidOperation, TypeError):
        return Response({"detail": "Enter a valid price, compare price and non-negative stock quantity."}, status=400)

    if prof["role"] == "vendor":
        # Seller accounts can never choose a different seller's store from request data.
        with connection.cursor() as c:
            c.execute(
                "select id from public.vendors where owner_id=%s and status='approved' order by created_at limit 2",
                [user["id"]],
            )
            owned_stores = [str(row[0]) for row in c.fetchall()]
        if not owned_stores:
            return Response({"detail": "Your account has no approved store yet. Contact the administrator."}, status=403)
        requested_vendor = str(data.get("vendor_id") or "").strip()
        vendor = requested_vendor if requested_vendor in owned_stores else owned_stores[0]
        if vendor not in owned_stores:
            return Response({"detail": "You can only manage your own approved store."}, status=403)
    else:
        vendor = str(data.get("vendor_id") or "").strip()
        try:
            uuid.UUID(vendor)
        except (ValueError, TypeError, AttributeError):
            return Response({"detail": "Choose an approved store."}, status=400)
        if not allowed_store(vendor):
            return Response({"detail": "Choose an approved store you are allowed to manage."}, status=403)

    category = data.get("category_id") or None
    if category:
        try:
            uuid.UUID(str(category))
        except (ValueError, TypeError, AttributeError):
            return Response({"detail": "Invalid category."}, status=400)
        with connection.cursor() as c:
            c.execute("select id from public.categories where id=%s and is_active=true", [category])
            if not c.fetchone():
                return Response({"detail": "Choose an active category."}, status=400)

    sizes = data.get("sizes", [])
    colors = data.get("colors", [])
    if not isinstance(sizes, list) or not isinstance(colors, list):
        return Response({"detail": "Sizes and colours must be arrays."}, status=400)
    raw_size_prices = data.get("size_prices", {})
    if raw_size_prices is None: raw_size_prices = {}
    if not isinstance(raw_size_prices, dict):
        return Response({"detail": "Size prices must be a map of size to price."}, status=400)
    size_prices = {}
    try:
        for size_key, size_value in raw_size_prices.items():
            normalized_size = str(size_key)[:30]
            if normalized_size not in [str(x)[:30] for x in sizes]: continue
            normalized_price = Decimal(str(size_value))
            if not normalized_price.is_finite() or normalized_price < 0: raise ValueError()
            size_prices[normalized_size] = str(normalized_price.quantize(Decimal("0.01")))
    except (ValueError, InvalidOperation, TypeError):
        return Response({"detail": "Enter valid non-negative prices for each size."}, status=400)
    image_url = str(data.get("image_url", "")).strip()
    image_public_id = str(data.get("image_public_id", "")).strip()
    additional_description = str(data.get("additional_description", ""))[:12000]
    if image_url and (not image_url.startswith("https://res.cloudinary.com/") or len(image_url) > 1000):
        return Response({"detail": "Upload the image through the configured Cloudinary uploader."}, status=400)
    extra_images = data.get("extra_images", [] if request.method == "POST" else None)
    if extra_images is not None:
        if not isinstance(extra_images, list) or len(extra_images) > 8:
            return Response({"detail": "Upload up to 8 additional product images."}, status=400)
        normalized_images = []
        for index, image in enumerate(extra_images):
            if not isinstance(image, dict):
                return Response({"detail": "Each gallery image must be a valid image object."}, status=400)
            url = str(image.get("image_url", "")).strip()
            public_id = str(image.get("image_public_id", "")).strip()
            alt_text = str(image.get("alt_text") or name)[:180]
            if not url.startswith("https://res.cloudinary.com/") or len(url) > 1000 or not public_id or len(public_id) > 255:
                return Response({"detail": "Upload each gallery image through the configured Cloudinary uploader."}, status=400)
            normalized_images.append((url, public_id, alt_text, index))
        extra_images = normalized_images

    try:
        with transaction.atomic():
            with connection.cursor() as c:
                if request.method == "PATCH":
                    product_id = str(data.get("id") or "").strip()
                    try:
                        uuid.UUID(product_id)
                    except (ValueError, TypeError, AttributeError):
                        return Response({"detail": "Choose a valid product to edit."}, status=400)
                    if prof["role"] == "vendor":
                        c.execute(
                            """select p.id from public.products p join public.vendors v on v.id=p.vendor_id
                               where p.id=%s and v.owner_id=%s and v.status='approved'""",
                            [product_id, user["id"]],
                        )
                    else:
                        c.execute(
                            """select p.id from public.products p join public.vendors v on v.id=p.vendor_id
                               where p.id=%s and v.status='approved'""",
                            [product_id],
                        )
                    if not c.fetchone():
                        return Response({"detail": "Product not found or you do not have permission to edit it."}, status=404)
                    c.execute(
                        """update public.products set vendor_id=%s,category_id=%s,name=%s,
                           description=%s,additional_description=%s,price=%s,compare_at_price=%s,
                           image_url=%s,image_public_id=%s,sizes=%s,colors=%s,stock_quantity=%s,size_prices=%s::jsonb,updated_at=now()
                           where id=%s returning id,name,slug,price,stock_quantity,image_url,is_active,vendor_id""",
                        [vendor, category, name, str(data.get("description", ""))[:4000],
                         additional_description, price, compare_price, image_url, image_public_id,
                         [str(x)[:30] for x in sizes], [str(x)[:50] for x in colors], stock, json.dumps(size_prices), product_id],
                    )
                else:
                    slug = slugify(name)[:150] + "-" + uuid.uuid4().hex[:8]
                    c.execute(
                        """insert into public.products(vendor_id,category_id,name,slug,description,
                           additional_description,price,compare_at_price,image_url,image_public_id,
                           sizes,colors,stock_quantity,size_prices,is_active)
                           values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,true)
                           returning id,name,slug,price,stock_quantity,image_url,is_active,vendor_id""",
                        [vendor, category, name, slug, str(data.get("description", ""))[:4000],
                         additional_description, price, compare_price, image_url, image_public_id,
                         [str(x)[:30] for x in sizes], [str(x)[:50] for x in colors], stock, json.dumps(size_prices)],
                    )
                row = c.fetchone()
                saved_product_id = str(row[0])
                if extra_images is not None:
                    c.execute("delete from public.product_images where product_id=%s", [saved_product_id])
                    for image_url_value, image_public_id_value, alt_text_value, sort_order_value in extra_images:
                        c.execute(
                            """insert into public.product_images
                               (product_id,image_url,image_public_id,alt_text,sort_order)
                               values(%s,%s,%s,%s,%s)""",
                            [saved_product_id, image_url_value, image_public_id_value, alt_text_value, sort_order_value],
                        )
        return Response({
            "id": str(row[0]), "name": row[1], "slug": row[2], "price": str(row[3]),
            "stock_quantity": row[4], "image_url": row[5], "is_active": row[6],
            "vendor_id": str(row[7]),
        }, status=201 if request.method == "POST" else 200)
    except Exception:
        return Response({"detail": "Product could not be saved. Verify the category, vendor and database settings."}, status=400)
