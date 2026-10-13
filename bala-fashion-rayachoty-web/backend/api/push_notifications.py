"""Firebase Cloud Messaging device registration and best-effort server push."""
import json
import logging
import os

from django.db import connection
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .views import _role_user

logger = logging.getLogger(__name__)
_firebase_app = None


def _messaging():
    """Initialize Firebase Admin only when a server-side service account is configured."""
    global _firebase_app
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging
        if _firebase_app is None:
            config = json.loads(raw)
            try:
                _firebase_app = firebase_admin.get_app()
            except ValueError:
                _firebase_app = firebase_admin.initialize_app(credentials.Certificate(config))
        return messaging
    except Exception:
        logger.exception("Firebase Admin push is not configured correctly")
        return None


def send_push_to_user(user_id, title, body, order_id=None, event_type="update"):
    """Send a push to all registered devices; missing push credentials never break orders."""
    messaging = _messaging()
    if messaging is None:
        return
    try:
        with connection.cursor() as cursor:
            cursor.execute("select token from public.push_notification_devices where user_id=%s", [str(user_id)])
            tokens = [row[0] for row in cursor.fetchall()]
        for token in tokens:
            try:
                messaging.send(messaging.Message(
                    notification=messaging.Notification(title=str(title)[:120], body=str(body)[:240]),
                    data={
                        "title": str(title)[:120],
                        "body": str(body)[:240],
                        "orderId": str(order_id or ""),
                        "eventType": str(event_type)[:40],
                        "url": "/orders",
                    },
                    token=token,
                    webpush=messaging.WebpushConfig(
                        notification=messaging.WebpushNotification(
                            icon="/b-tech-logo.png",
                            badge="/b-tech-logo.png",
                            require_interaction=False,
                        )
                    ),
                ))
            except Exception as exc:
                # Stale or invalid tokens should not prevent delivery to other devices.
                logger.warning("Push send failed for a registered device (%s)", type(exc).__name__)
    except Exception:
        logger.exception("Could not read registered push devices")


@api_view(["POST", "DELETE"])
def notification_devices(request):
    """Register/revoke the signed-in user's FCM web-push token."""
    user, profile, error = _role_user(request, {"customer", "vendor", "admin", "delivery_boy"})
    if error:
        return error
    token = str(request.data.get("token") or "").strip()
    if not token or len(token) > 4096:
        return Response({"detail": "A valid browser push token is required."}, status=400)
    try:
        with connection.cursor() as cursor:
            if request.method == "POST":
                cursor.execute(
                    """insert into public.push_notification_devices(user_id,token,platform,updated_at)
                       values(%s,%s,'web',now())
                       on conflict(token) do update set user_id=excluded.user_id,
                         platform='web',updated_at=now()""",
                    [user["id"], token],
                )
                return Response({"registered": True})
            cursor.execute(
                "delete from public.push_notification_devices where user_id=%s and token=%s",
                [user["id"], token],
            )
        return Response({"registered": False})
    except Exception:
        logger.exception("Could not save push notification device")
        return Response({"detail": "Could not save this browser for push notifications."}, status=503)
