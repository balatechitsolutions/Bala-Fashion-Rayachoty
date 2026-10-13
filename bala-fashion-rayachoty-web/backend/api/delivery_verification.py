import hashlib
import hmac
import secrets

from django.conf import settings
from django.core.mail import send_mail
from django.db import connection, transaction
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .views import _insert_account_notification, _notify_admins, _role_user


@api_view(["POST"])
def delivery_verification(request):
    user, profile, error = _role_user(request, {"delivery_boy"})
    if error:
        return error
    order_id = str(request.data.get("order_id") or "").strip()
    action = str(request.data.get("action") or "").strip().lower()
    try:
        import uuid
        order_id = str(uuid.UUID(order_id))
    except (ValueError, TypeError, AttributeError):
        return Response({"detail": "Choose a valid assigned order."}, status=400)

    try:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                """select o.id,o.order_number,o.status,o.payment_method,o.payment_status,o.customer_id
                   from public.orders o
                   where o.id=%s and o.assigned_delivery_boy_id=%s for update""",
                [order_id, user["id"]],
            )
            order = cursor.fetchone()
            if not order:
                return Response({"detail": "Order not found or not assigned to your account."}, status=404)

            if action == "start":
                if order[2] != "packed":
                    return Response({"detail": "Only packed orders can be marked out for delivery."}, status=409)
                if not settings.EMAIL_HOST or not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
                    return Response({"detail": "Email delivery is not configured on the backend. Configure SMTP environment variables on Render."}, status=503)
                cursor.execute("select email from auth.users where id=%s", [order[5]])
                email_row = cursor.fetchone()
                recipient = str(email_row[0] or "").strip() if email_row else ""
                if not recipient:
                    return Response({"detail": "The customer has no registered email address."}, status=400)
                code = f"{secrets.randbelow(1000000):06d}"
                digest = hashlib.sha256(f"{order_id}:{code}".encode()).hexdigest()
                send_mail(
                    f"Bala Fashion delivery code — {order[1]}",
                    f"Your order {order[1]} is out for delivery. Give this six-digit code to the delivery person only after receiving your order: {code}. It expires in 15 minutes. Do not share it before the order arrives.",
                    settings.DEFAULT_FROM_EMAIL,
                    [recipient],
                    fail_silently=False,
                )
                cursor.execute(
                    """update public.orders set status='out_for_delivery',delivery_otp_hash=%s,
                       delivery_otp_expires_at=now()+interval '15 minutes',delivery_otp_sent_at=now(),
                       delivery_otp_attempts=0,updated_at=now() where id=%s""",
                    [digest, order_id],
                )
                return Response({"order_id": order_id, "status": "out_for_delivery", "detail": f"OTP sent to {recipient}."})

            if action != "verify":
                return Response({"detail": "Choose start or verify action."}, status=400)
            if order[2] != "out_for_delivery":
                return Response({"detail": "The order must be out for delivery before OTP verification."}, status=409)
            code = str(request.data.get("otp") or "").strip()
            if len(code) != 6 or not code.isdigit():
                return Response({"detail": "Enter the six-digit code from the customer's registered email."}, status=400)
            cursor.execute(
                "select delivery_otp_hash,delivery_otp_expires_at,delivery_otp_attempts from public.orders where id=%s",
                [order_id],
            )
            row = cursor.fetchone()
            if not row or not row[0] or not row[1]:
                return Response({"detail": "No active code. Ask an administrator to restart delivery."}, status=409)
            if row[1] <= timezone.now():
                return Response({"detail": "The code expired. Ask an administrator to restart delivery."}, status=409)
            if int(row[2] or 0) >= 5:
                return Response({"detail": "Five incorrect attempts reached. Ask an administrator for help."}, status=429)
            candidate = hashlib.sha256(f"{order_id}:{code}".encode()).hexdigest()
            if not hmac.compare_digest(str(row[0]), candidate):
                cursor.execute("update public.orders set delivery_otp_attempts=delivery_otp_attempts+1 where id=%s", [order_id])
                return Response({"detail": "Incorrect code. Check the customer's email and try again."}, status=400)
            cursor.execute(
                """update public.orders set status='delivered',delivery_otp_hash=NULL,delivery_otp_expires_at=NULL,
                   payment_status=case when payment_method='cod' and payment_status='pending' then 'paid' else payment_status end,
                   updated_at=now() where id=%s returning id,order_number,status,payment_status,total,created_at""",
                [order_id],
            )
            updated = cursor.fetchone()
            _insert_account_notification(cursor, order[5], "delivered", "Your order was delivered",
                                         f"Order {order[1]} has been delivered.", order[0])
            _notify_admins(cursor, "delivered", "Order delivered",
                           f"Order {order[1]} was delivered after OTP verification.", order[0])
        return Response({"id": str(updated[0]), "order_number": updated[1], "status": updated[2],
                         "payment_status": updated[3], "total": str(updated[4]),
                         "created_at": updated[5].isoformat() if hasattr(updated[5], "isoformat") else updated[5]})
    except Exception:
        return Response({"detail": "Delivery verification failed. Check backend email settings and Render logs."}, status=503)
