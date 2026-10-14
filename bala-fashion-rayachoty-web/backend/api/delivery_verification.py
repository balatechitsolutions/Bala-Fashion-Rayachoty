import os
import re
import math
import hashlib
import logging
import hmac
import secrets

from django.conf import settings
from django.core.mail import send_mail
from django.db import connection, transaction
from django.utils import timezone
import requests
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .views import _insert_account_notification, _notify_admins, _role_user

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

            if action in {"start", "resend", "mailjet"}:
                if action == "start" and order[2] != "packed":
                    return Response({"detail": "Only packed orders can be marked out for delivery."}, status=409)
                if action == "resend" and order[2] != "out_for_delivery":
                    return Response({"detail": "A verification code can only be resent for an order already out for delivery."}, status=409)
                if action == "mailjet" and order[2] not in {"packed", "out_for_delivery"}:
                    return Response({"detail": "Mailjet OTP is available only for packed or out-for-delivery orders."}, status=409)

                if action == "start":
                    address = order[6] if isinstance(order[6], dict) else {}
                    recipient_name = str(address.get("recipient_name") or "").strip()
                    phone = str(address.get("phone") or "").strip()
                    line1 = str(address.get("line1") or "").strip()
                    phone_valid = bool(re.fullmatch(r"[0-9+() \-]{10,16}", phone)) and 10 <= sum(ch.isdigit() for ch in phone) <= 15
                    try:
                        latitude = float(address.get("latitude"))
                        longitude = float(address.get("longitude"))
                        coordinates_valid = (
                            math.isfinite(latitude) and math.isfinite(longitude)
                            and -90 <= latitude <= 90 and -180 <= longitude <= 180
                        )
                    except (TypeError, ValueError, OverflowError):
                        coordinates_valid = False
                    missing = []
                    if not recipient_name:
                        missing.append("customer name")
                    if not phone_valid:
                        missing.append("valid customer phone number")
                    if not line1:
                        missing.append("complete delivery address")
                    if not coordinates_valid:
                        missing.append("valid delivery map location")
                    if missing:
                        return Response({
                            "detail": "Delivery cannot start. Ask the administrator to correct and verify the order's saved delivery address: " + ", ".join(missing) + "."
                        }, status=409)

                cursor.execute("select email from auth.users where id=%s", [order[5]])
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

                # Try SMTP first, then automatically fall back to Mailjet so delivery
                # staff are not forced to switch providers manually when Render blocks SMTP.
                sent = False
                provider = ""
                smtp_detail = ""
                if action in {"start", "resend"}:
                    if settings.EMAIL_HOST and settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD:
                        try:
                            sent = send_mail(
                                subject, body, settings.DEFAULT_FROM_EMAIL, [recipient],
                                fail_silently=False,
                            ) == 1
                            if sent:
                                provider = "SMTP"
                            else:
                                smtp_detail = "SMTP did not accept the message."
                                logger.warning("SMTP returned zero sent messages for delivery OTP order %s", order_id)
                        except Exception as exc:
                            smtp_detail = "SMTP network/send failure."
                            logger.warning("Delivery OTP SMTP send failed for order %s (%s); trying Mailjet fallback.", order_id, type(exc).__name__)
                    else:
                        smtp_detail = "SMTP is not configured."
                    if not sent:
                        sent, mailjet_detail, provider = _send_mailjet_otp(recipient, subject, body, order_id)
                        if not sent:
                            return Response({
                                "detail": f"{smtp_detail} {mailjet_detail} Configure Mailjet credentials and verify the sender in Render."
                            }, status=503)
                else:
                    sent, mailjet_detail, provider = _send_mailjet_otp(recipient, subject, body, order_id)
                    if not sent:
                        return Response({"detail": mailjet_detail}, status=503)

                cursor.execute(
                    """update public.orders set status='out_for_delivery',delivery_otp_hash=%s,
                       delivery_otp_expires_at=now()+interval '15 minutes',delivery_otp_sent_at=now(),
                       delivery_otp_attempts=0,updated_at=now() where id=%s""",
                    [digest, order_id],
                )
                return Response({
                    "order_id": order_id, "status": "out_for_delivery",
                    "provider": provider, "detail": f"OTP sent to the customer's registered email using {provider}."
                })

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
        logger.exception("Delivery verification failed for order %s (action=%s)", order_id, action)
        return Response({"detail": "Delivery verification failed. The backend error was logged; check Render application logs for the traceback."}, status=503)
