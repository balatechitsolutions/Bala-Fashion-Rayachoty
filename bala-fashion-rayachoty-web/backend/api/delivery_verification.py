import os
import re
import math
import hashlib
import logging
import hmac
import secrets

from django.db import connection, transaction
from django.utils import timezone
import requests
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .views import _insert_account_notification, _notify_admins, _order_address_issues, _role_user

logger = logging.getLogger(__name__)


def _send_mailjet_otp(recipient, subject, body, order_id):
    """Send through Mailjet and return a safe status without exposing credentials."""
    key = os.getenv("MAILJET_API_KEY", "").strip()
    secret = os.getenv("MAILJET_API_SECRET", "").strip()
    sender = os.getenv("MAILJET_SENDER_EMAIL", "").strip()
    sender_name = os.getenv("MAILJET_SENDER_NAME", "Bala Fashion").strip() or "Bala Fashion"
    if not (key and secret and sender):
        return False, "Mailjet fallback is not configured on Render.", ""
    try:
        response = requests.post(
            "https://api.mailjet.com/v3.1/send",
            auth=(key, secret),
            json={"Messages": [{
                "From": {"Email": sender, "Name": sender_name},
                "To": [{"Email": recipient}],
                "Subject": subject,
                "TextPart": body,
            }]},
            timeout=15,
        )
        payload = response.json() if response.content else {}
        messages = payload.get("Messages", [])
        sent = response.ok and bool(messages and messages[0].get("Status") == "success")
        if sent:
            return True, "", "Mailjet"
        logger.error("Mailjet delivery OTP rejected for order %s (HTTP %s)", order_id, response.status_code)
        return False, "Mailjet rejected the OTP. Check API credentials and sender verification.", ""
    except Exception as exc:
        logger.warning("Mailjet OTP fallback failed for order %s (%s)", order_id, type(exc).__name__)
        return False, "Mailjet could not be reached. Check Render network access and Mailjet settings.", ""


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
                """select o.id,o.order_number,o.status,o.payment_method,o.payment_status,o.customer_id,
                          coalesce(o.address_snapshot, '{}'::jsonb)
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
                address = order[6]
                if isinstance(address, str):
                    try:
                        import json
                        address = json.loads(address)
                    except (TypeError, ValueError):
                        address = {}
                address = address if isinstance(address, dict) else {}
                missing = _order_address_issues(address)
                if missing:
                    return Response({"detail": "Delivery address needs correction: " + ", ".join(missing) + "."}, status=409)
                cursor.execute("UPDATE public.orders SET status='out_for_delivery', delivery_otp_hash=NULL, delivery_otp_expires_at=NULL, delivery_otp_attempts=0, updated_at=now() WHERE id=%s", [order_id])
                return Response({"order_id": order_id, "status": "out_for_delivery", "detail": f"{order[1]} marked out for delivery. Send the customer OTP separately."})

            if action in {"send", "resend", "mailjet"}:
                if order[2] != "out_for_delivery":
                    return Response({"detail": "Mark the order out for delivery before sending a verification OTP."}, status=409)
4464                cursor.execute("select email from auth.users where id=%s", [order[5]])
                email_row = cursor.fetchone()
                recipient = str(email_row[0] or "").strip() if email_row else ""
                if not recipient:
                    return Response({"detail": "The customer has no registered email address."}, status=400)

                code = f"{secrets.randbelow(1000000):06d}"
                digest = hashlib.sha256(f"{order_id}:{code}".encode()).hexdigest()
                subject = f"Bala Fashion delivery code — {order[1]}"
                body = (
                    f"Your order {order[1]} is out for delivery. Give this six-digit code to "
                    f"the delivery person only after receiving your order: {code}. "
                    "It expires in 15 minutes. Do not share it before the order arrives."
                )

                # Use Mailjet's HTTPS API exclusively. Render Free blocks outbound SMTP.
                sent, mailjet_detail, provider = _send_mailjet_otp(
                    recipient, subject, body, order_id
                )
                if not sent:
                    logger.error(
                        "Delivery OTP failed for order %s. Mailjet: %s",
                        order_id, mailjet_detail,
                    )
                    return Response({
                        "detail": (
                            f"{mailjet_detail} Check MAILJET_API_KEY, MAILJET_API_SECRET, "
                            "MAILJET_SENDER_EMAIL, and sender verification in Render/Mailjet."
                        )
                    }, status=503)

                cursor.execute(
                    """update public.orders set delivery_otp_hash=%s,
                       delivery_otp_expires_at=now()+interval '15 minutes',delivery_otp_sent_at=now(),
                       delivery_otp_attempts=0,updated_at=now() where id=%s""",
                    [digest, order_id],
                )
                return Response({
                    "order_id": order_id, "status": "out_for_delivery",
                    "provider": provider, "detail": f"OTP sent to the customer's registered email using {provider}."
                })

            if action != "verify":
                return Response({"detail": "Choose start, send, resend, or verify action."}, status=400)
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
        logger.exception("Delivery verification failed for order %s (action=%s)", order_id, action)
        return Response({"detail": "Delivery verification failed. The backend error was logged; check Render application logs for the traceback."}, status=503)
