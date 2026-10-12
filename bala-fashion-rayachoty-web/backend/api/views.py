import json, os, re, uuid
from decimal import Decimal, InvalidOperation
import requests
from django.db import connection, transaction
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
DELIVERY_FEE=Decimal(os.getenv("DELIVERY_FEE","0"))

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
    try:
        if not os.getenv("DATABASE_URL"): return Response({"status":"ok","database":"not_configured"})
        with connection.cursor() as c:c.execute("select 1");c.fetchone()
        return Response({"status":"ok","service":"bala-fashion-api","database":"connected"})
    except Exception:
        return Response({"status":"degraded","database":"unavailable"},status=503)

@api_view(["GET"])
def categories(request):
    try:
        with connection.cursor() as c:
            c.execute("select id,name,slug,image_url,sort_order from public.categories where is_active=true order by sort_order,name")
            return Response(_rows(c))
    except Exception:return Response({"detail":"Categories are temporarily unavailable."},status=503)

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
                c.execute("select id,name,slug,image_url,sort_order,is_active from public.categories order by sort_order,name")
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
                c.execute(
                    "insert into public.categories(name,slug,image_url,sort_order,is_active) values(%s,%s,%s,%s,true) returning id,name,slug,image_url,sort_order,is_active",
                    [name, slug, image_url, sort_order],
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
                if "is_active" in data:
                    if not isinstance(data["is_active"], bool):
                        return Response({"detail": "is_active must be true or false."}, status=400)
                    fields.append("is_active=%s"); params.append(data["is_active"])
                if not fields:
                    return Response({"detail": "Provide category fields to update."}, status=400)
                params.append(category_id)
                c.execute(
                    f"update public.categories set {', '.join(fields)} where id=%s returning id,name,slug,image_url,sort_order,is_active",
                    params,
                )
            row = c.fetchone()
        if not row:
            return Response({"detail": "Category not found."}, status=404)
        return Response({"id": str(row[0]), "name": row[1], "slug": row[2], "image_url": row[3], "sort_order": row[4], "is_active": row[5]}, status=201 if request.method == "POST" else 200)
    except Exception:
        return Response({"detail": "Category could not be saved. Check for duplicate category names or slugs and retry."}, status=503)


@api_view(["GET", "POST", "PATCH"])
def manage_vendors(request):
    user, prof, error = _role_user(request, {"admin"})
    if error:
        return error
    if request.method == "GET":
        try:
            with connection.cursor() as c:
                c.execute(
                    """select v.id,v.owner_id,v.name,v.slug,v.description,v.logo_url,v.phone,v.address,
                              v.status,v.created_at,p.full_name as owner_name,p.phone as owner_phone
                       from public.vendors v
                       left join public.profiles p on p.id=v.owner_id
                       order by case v.status when 'pending' then 0 when 'approved' then 1 else 2 end, v.created_at desc
                       limit 500"""
                )
                return Response({"results": _rows(c)})
        except Exception:
            return Response({"detail": "Vendor list could not be loaded."}, status=503)

    if request.method == "POST":
        data = request.data
        owner_id = str(data.get("owner_id", "")).strip()
        try:
            owner_uuid = uuid.UUID(owner_id)
        except (ValueError, TypeError, AttributeError):
            return Response({"detail": "Enter the vendor owner's valid Supabase Auth UUID."}, status=400)
        name = str(data.get("name", "")).strip()[:180]
        if not name:
            return Response({"detail": "Store/vendor name is required."}, status=400)
        phone = str(data.get("phone", "")).strip()[:30]
        address = str(data.get("address", "")).strip()[:500]
        description = str(data.get("description", "")).strip()[:2000]
        requested_status = str(data.get("status", "pending")).strip().lower()
        if requested_status not in {"pending", "approved", "rejected", "suspended"}:
            return Response({"detail": "Status must be pending, approved, rejected or suspended."}, status=400)
        base_slug = slugify(name)[:240].strip("-")
        if not base_slug:
            return Response({"detail": "Enter a valid vendor/store name."}, status=400)
        try:
            with transaction.atomic():
                with connection.cursor() as c:
                    # Check the UUID against Supabase Auth itself, not a Django integer ID.
                    c.execute("select id, coalesce(raw_user_meta_data->>'full_name','') from auth.users where id=%s", [str(owner_uuid)])
                    auth_user = c.fetchone()
                    if not auth_user:
                        return Response({"detail": "No Supabase Auth user exists for that UUID. Copy the user's UUID from Supabase Authentication."}, status=400)
                    c.execute(
                        """insert into public.profiles(id,full_name,phone,role)
                           values(%s,%s,%s,'vendor')
                           on conflict(id) do update set
                             full_name=case when excluded.full_name<>'' then excluded.full_name else public.profiles.full_name end,
                             phone=case when excluded.phone<>'' then excluded.phone else public.profiles.phone end,
                             role=case when public.profiles.role='customer' then 'vendor' else public.profiles.role end,
                             updated_at=now()""",
                        [str(owner_uuid), str(auth_user[1] or "")[:120], phone],
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
                        """insert into public.vendors(owner_id,name,slug,description,phone,address,status)
                           values(%s,%s,%s,%s,%s,%s,%s)
                           returning id,owner_id,name,slug,description,logo_url,phone,address,status,created_at""",
                        [str(owner_uuid), name, slug, description, phone, address, requested_status],
                    )
                    row = c.fetchone()
            result = {key: value for key, value in zip(
                ["id","owner_id","name","slug","description","logo_url","phone","address","status","created_at"], row
            )}
            result["id"] = str(result["id"])
            result["owner_id"] = str(result["owner_id"])
            if hasattr(result["created_at"], "isoformat"):
                result["created_at"] = result["created_at"].isoformat()
            return Response(result, status=201)
        except Exception:
            return Response({"detail": "Vendor could not be created. Confirm the UUID belongs to an existing Supabase Auth user and that the database schema is up to date."}, status=503)

    vendor_id = str(request.data.get("id", "")).strip()
    try:
        uuid.UUID(vendor_id)
    except (ValueError, TypeError, AttributeError):
        return Response({"detail": "Choose a valid vendor."}, status=400)
    status_value = str(request.data.get("status", "")).strip().lower()
    if status_value not in {"pending", "approved", "rejected", "suspended"}:
        return Response({"detail": "Status must be pending, approved, rejected or suspended."}, status=400)
    try:
        with connection.cursor() as c:
            c.execute("update public.vendors set status=%s where id=%s returning id,name,slug,status,owner_id", [status_value, vendor_id])
            row = c.fetchone()
        if not row:
            return Response({"detail": "Vendor not found."}, status=404)
        return Response({"id": str(row[0]), "name": row[1], "slug": row[2], "status": row[3], "owner_id": str(row[4]) if row[4] else None})
    except Exception:
        return Response({"detail": "Vendor status could not be updated."}, status=503)

@api_view(["GET"])
def products(request):
    search=request.query_params.get("search","").strip()[:100]
    category=request.query_params.get("category","").strip()[:80]
    limit=min(int(request.query_params.get("limit","30")) if request.query_params.get("limit","30").isdigit() else 30,100)
    where=["p.is_active=true","v.status='approved'"]; params=[]
    if search:
        where.append("(p.name ilike %s or p.description ilike %s or v.name ilike %s)")
        params += [f"%{search}%"]*3
    if category:where.append("c.slug=%s");params.append(category)
    params.append(max(1,limit))
    try:
        with connection.cursor() as c:
            c.execute(f"""select p.id,p.name,p.slug,p.description,p.price,p.compare_at_price,p.image_url,p.image_public_id,p.sizes,p.colors,p.stock_quantity,p.category_id,c.name as category_name,c.slug as category_slug,p.vendor_id,v.name as vendor_name,v.slug as vendor_slug from public.products p join public.vendors v on v.id=p.vendor_id left join public.categories c on c.id=p.category_id where {' and '.join(where)} order by p.created_at desc limit %s""",params)
            rows=_rows(c)
        return Response({"results":rows,"count":len(rows)})
    except Exception:return Response({"detail":"Products are unavailable. Check the backend database connection."},status=503)

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

@api_view(["GET","POST"])
def orders(request):
    user,error=_user(request)
    if error:return error
    if request.method=="GET":
        try:
            with connection.cursor() as c:
                c.execute("""select o.id,o.order_number,o.status,o.payment_method,o.payment_status,o.subtotal,o.delivery_fee,o.total,o.created_at,o.address_snapshot,o.notes,coalesce(json_agg(json_build_object('product_id',oi.product_id,'product_name',oi.product_name,'image_url',oi.image_url,'quantity',oi.quantity,'size',oi.size,'color',oi.color,'unit_price',oi.unit_price,'line_total',oi.line_total)) filter(where oi.id is not null),'[]'::json) as items from public.orders o left join public.order_items oi on oi.order_id=o.id where o.customer_id=%s group by o.id order by o.created_at desc limit 50""",[user["id"]])
                rows=_rows(c)
            return Response({"results":rows,"count":len(rows)})
        except Exception:return Response({"detail":"Order history is unavailable."},status=503)
    data=request.data;address=data.get("address");items=data.get("items")
    if not isinstance(address,dict) or not isinstance(items,list) or not 1<=len(items)<=30:return Response({"detail":"Provide a delivery address and 1–30 cart items."},status=400)
    recipient=str(address.get("recipient_name","")).strip()[:120];phone=str(address.get("phone","")).strip()[:30];line1=str(address.get("line1","")).strip()[:200]
    if not recipient or not line1 or not re.fullmatch(r"[0-9+() \-]{10,16}",phone):return Response({"detail":"Enter recipient name, valid mobile number and street address."},status=400)
    snapshot={"recipient_name":recipient,"phone":phone,"line1":line1,"line2":str(address.get("line2",""))[:200],"landmark":str(address.get("landmark",""))[:160],"city":str(address.get("city","Rayachoty"))[:100],"state":str(address.get("state","Andhra Pradesh"))[:100],"postal_code":str(address.get("postal_code",""))[:12]}
    try:
        with transaction.atomic():
            vendor=None;subtotal=Decimal("0.00");verified=[];seen=set()
            for raw in items:
                pid=str(raw.get("product_id",""))
                try:uuid.UUID(pid);qty=int(raw.get("quantity",0))
                except (ValueError,TypeError,AttributeError):return Response({"detail":"Cart has invalid product ID or quantity."},status=400)
                if not 1<=qty<=20:return Response({"detail":"Each quantity must be between 1 and 20."},status=400)
                if pid in seen:return Response({"detail":"Combine duplicate cart lines before checkout."},status=400)
                seen.add(pid)
                with connection.cursor() as c:
                    c.execute("""select p.id,p.name,p.price,p.image_url,p.stock_quantity,p.sizes,p.colors,p.vendor_id from public.products p join public.vendors v on v.id=p.vendor_id where p.id=%s and p.is_active=true and v.status='approved' for update of p""",[pid])
                    row=c.fetchone()
                if not row:return Response({"detail":"A product is no longer available."},status=409)
                prod_id,name,price,image,stock,sizes,colors,vendor_id=row
                if stock<qty:return Response({"detail":f"Only {stock} left for {name}."},status=409)
                if vendor is None:vendor=vendor_id
                elif vendor!=vendor_id:return Response({"detail":"Please check out one seller at a time."},status=400)
                size=str(raw.get("size",""))[:30];color=str(raw.get("color",""))[:50]
                if sizes and size and size not in sizes:return Response({"detail":f"Size is unavailable for {name}."},status=409)
                if colors and color and color not in colors:return Response({"detail":f"Colour is unavailable for {name}."},status=409)
                line=(price*qty).quantize(Decimal("0.01"));subtotal+=line
                verified.append({"id":prod_id,"name":name,"price":price,"image":image or "","qty":qty,"size":size,"color":color,"line":line})
            if subtotal < Decimal("250.00"):
                return Response({"detail":"Minimum order amount is ₹250. Add more items to continue."},status=400)
            fee=max(Decimal("0.00"),DELIVERY_FEE);total=subtotal+fee;number="BFR-"+uuid.uuid4().hex[:10].upper()
            with connection.cursor() as c:
                c.execute("""insert into public.orders(order_number,customer_id,vendor_id,status,payment_method,payment_status,subtotal,delivery_fee,total,address_snapshot,notes) values(%s,%s,%s,'placed','cod','pending',%s,%s,%s,%s::jsonb,%s) returning id,order_number,status,payment_method,subtotal,delivery_fee,total,created_at""",[number,user["id"],vendor,subtotal,fee,total,json.dumps(snapshot),str(data.get("notes",""))[:500]])
                order=c.fetchone();order_id=order[0]
                for i in verified:
                    c.execute("update public.products set stock_quantity=stock_quantity-%s,updated_at=now() where id=%s and stock_quantity >= %s",[i["qty"],i["id"],i["qty"]])
                    if c.rowcount!=1:raise ValueError("Inventory changed during checkout. Please retry.")
                    c.execute("""insert into public.order_items(order_id,product_id,product_name,image_url,size,color,quantity,unit_price,line_total) values(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",[order_id,i["id"],i["name"],i["image"],i["size"],i["color"],i["qty"],i["price"],i["line"]])

                # Only the two requested events are persisted: placed and delivered.
                c.execute("select owner_id from public.vendors where id=%s", [str(vendor)])
                seller_row = c.fetchone()
                if seller_row and seller_row[0]:
                    _insert_account_notification(
                        c, seller_row[0], "placed", "New order placed",
                        f"Order {order[1]} has been placed.", order_id,
                    )
                _notify_admins(
                    c, "placed", "New order placed",
                    f"Order {order[1]} has been placed.", order_id,
                )
            return Response({"id":str(order[0]),"order_number":order[1],"status":order[2],"payment_method":order[3],"subtotal":str(order[4]),"delivery_fee":str(order[5]),"total":str(order[6]),"created_at":order[7].isoformat()},status=201)
    except ValueError as e:return Response({"detail":str(e)},status=409)
    except Exception:return Response({"detail":"Could not place order. Please retry or contact support."},status=503)


@api_view(["GET", "PATCH", "DELETE"])
def manage_orders(request):
    """Role-scoped order management: admins see all orders; vendors see their own."""
    user, prof, error = _role_user(request, {"vendor", "admin"})
    if error:
        return error

    if request.method in {"PATCH", "DELETE"}:
        order_id = str(request.data.get("id") or request.data.get("order_id") or request.query_params.get("id") or "").strip()
        try:
            uuid.UUID(order_id)
        except (ValueError, TypeError, AttributeError):
            return Response({"detail": "Choose a valid order."}, status=400)

        if request.method == "DELETE":
            # Permanent order deletion is restricted to administrators. Restore stock
            # only when the order was not delivered, since delivered goods left inventory.
            if prof["role"] != "admin":
                return Response({"detail": "Only administrators can delete orders."}, status=403)
            try:
                with transaction.atomic():
                    with connection.cursor() as c:
                        c.execute("select id, order_number, status from public.orders where id=%s for update", [order_id])
                        existing = c.fetchone()
                        if not existing:
                            return Response({"detail": "Order not found."}, status=404)
                        if existing[2] != "delivered":
                            c.execute(
                                "select product_id, quantity from public.order_items where order_id=%s and product_id is not null",
                                [order_id],
                            )
                            for product_id, quantity in c.fetchall():
                                c.execute(
                                    "update public.products set stock_quantity=stock_quantity+%s, updated_at=now() where id=%s",
                                    [quantity, product_id],
                                )
                        c.execute("delete from public.order_items where order_id=%s", [order_id])
                        c.execute("delete from public.orders where id=%s", [order_id])
                return Response({"id": str(existing[0]), "order_number": existing[1], "detail": "Order permanently deleted."})
            except Exception:
                return Response({"detail": "Order could not be deleted. No changes were committed; please retry."}, status=503)

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
                    else:
                        c.execute("select id, status, payment_method, payment_status, customer_id, order_number from public.orders where id=%s for update", [order_id])
                    current = c.fetchone()
                    if not current:
                        return Response({"detail": "Order not found or you do not have permission to manage it."}, status=404)

                    current_status = current[1]
                    transitions = {
                        "placed": {"confirmed", "cancelled"},
                        "confirmed": {"packed", "cancelled"},
                        "packed": {"out_for_delivery"},
                        "out_for_delivery": {"delivered"},
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
                              o.subtotal,o.delivery_fee,o.total,o.address_snapshot,o.notes,o.created_at,
                              v.name as vendor_name,
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
                              o.subtotal,o.delivery_fee,o.total,o.address_snapshot,o.notes,o.created_at,
                              v.name as vendor_name,
                              coalesce(json_agg(json_build_object(
                                'product_name',oi.product_name,'image_url',oi.image_url,
                                'quantity',oi.quantity,'size',oi.size,'color',oi.color,
                                'line_total',oi.line_total
                              )) filter(where oi.id is not null),'[]'::json) as items
                       from public.orders o
                       join public.vendors v on v.id=o.vendor_id
                       left join public.order_items oi on oi.order_id=o.id
                       group by o.id,v.name order by o.created_at desc limit 200"""
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
    if folder not in {"bala-fashion/products","bala-fashion/categories"}:
        return Response({"detail":"Invalid upload folder."},status=400)
    if prof["role"] == "vendor" and folder != "bala-fashion/products":
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
    try:
        with connection.cursor() as c:
            if prof["role"] == "vendor":
                c.execute(
                    "select id,name,slug,status,logo_url from public.vendors where owner_id=%s order by name",
                    [user["id"]],
                )
            else:
                c.execute(
                    "select id,name,slug,status,logo_url from public.vendors order by name"
                )
            stores = _rows(c)
            if prof["role"] == "vendor":
                stores = [store for store in stores if store["status"] == "approved"]
            store_ids = [store["id"] for store in stores]
            if not store_ids:
                return Response({
                    "role": prof["role"], "stores": [], "products": [],
                    "orders": [], "stats": {"products": 0, "active_products": 0, "low_stock": 0, "orders": 0},
                })
            c.execute(
                """select p.id,p.name,p.slug,p.description,p.price,p.compare_at_price,
                          p.image_url,p.image_public_id,p.sizes,p.colors,p.stock_quantity,
                          p.category_id,p.vendor_id,p.is_active,p.created_at,
                          c.name as category_name,v.name as vendor_name
                   from public.products p
                   left join public.categories c on c.id=p.category_id
                   join public.vendors v on v.id=p.vendor_id
                   where p.vendor_id = any(%s) and v.status='approved'
                   order by p.created_at desc limit 200""",
                [store_ids],
            )
            managed_products = _rows(c)
            c.execute(
                """select o.id,o.order_number,o.status,o.payment_status,o.total,o.created_at,
                          v.name as vendor_name,o.payment_method,o.subtotal,o.delivery_fee,
                          o.address_snapshot,o.notes,
                          coalesce(json_agg(json_build_object(
                            'product_id',oi.product_id,'product_name',oi.product_name,
                            'image_url',oi.image_url,'quantity',oi.quantity,'size',oi.size,
                            'color',oi.color,'unit_price',oi.unit_price,'line_total',oi.line_total
                          )) filter(where oi.id is not null),'[]'::json) as items
                   from public.orders o
                   join public.vendors v on v.id=o.vendor_id
                   left join public.order_items oi on oi.order_id=o.id
                   where o.vendor_id = any(%s)
                   group by o.id,v.name order by o.created_at desc limit 50""",
                [store_ids],
            )
            managed_orders = _rows(c)
        return Response({
            "role": prof["role"], "stores": stores, "products": managed_products,
            "orders": managed_orders,
            "stats": {
                "products": len(managed_products),
                "active_products": sum(1 for p in managed_products if p["is_active"]),
                "low_stock": sum(1 for p in managed_products if int(p["stock_quantity"] or 0) <= 5),
                "orders": len(managed_orders),
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
                                  p.image_url,p.image_public_id,p.sizes,p.colors,p.stock_quantity,
                                  p.category_id,p.vendor_id,p.is_active,p.created_at,
                                  c.name as category_name,v.name as vendor_name
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
                                  p.image_url,p.image_public_id,p.sizes,p.colors,p.stock_quantity,
                                  p.category_id,p.vendor_id,p.is_active,p.created_at,
                                  c.name as category_name,v.name as vendor_name
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
    image_url = str(data.get("image_url", "")).strip()
    image_public_id = str(data.get("image_public_id", "")).strip()
    if image_url and (not image_url.startswith("https://res.cloudinary.com/") or len(image_url) > 1000):
        return Response({"detail": "Upload the image through the configured Cloudinary uploader."}, status=400)

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
                           description=%s,price=%s,compare_at_price=%s,image_url=%s,image_public_id=%s,
                           sizes=%s,colors=%s,stock_quantity=%s,updated_at=now()
                           where id=%s returning id,name,slug,price,stock_quantity,image_url,is_active,vendor_id""",
                        [vendor, category, name, str(data.get("description", ""))[:4000], price, compare_price,
                         image_url, image_public_id, [str(x)[:30] for x in sizes],
                         [str(x)[:50] for x in colors], stock, product_id],
                    )
                else:
                    slug = slugify(name)[:150] + "-" + uuid.uuid4().hex[:8]
                    c.execute(
                        """insert into public.products(vendor_id,category_id,name,slug,description,price,
                           compare_at_price,image_url,image_public_id,sizes,colors,stock_quantity,is_active)
                           values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true)
                           returning id,name,slug,price,stock_quantity,image_url,is_active,vendor_id""",
                        [vendor, category, name, slug, str(data.get("description", ""))[:4000], price,
                         compare_price, image_url, image_public_id, [str(x)[:30] for x in sizes],
                         [str(x)[:50] for x in colors], stock],
                    )
                row = c.fetchone()
        return Response({
            "id": str(row[0]), "name": row[1], "slug": row[2], "price": str(row[3]),
            "stock_quantity": row[4], "image_url": row[5], "is_active": row[6],
            "vendor_id": str(row[7]),
        }, status=201 if request.method == "POST" else 200)
    except Exception:
        return Response({"detail": "Product could not be saved. Verify the category, vendor and database settings."}, status=400)
