from celery import shared_task


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_account_push(self, user_id, title, body, order_id=None, event_type="update"):
    """Send push notifications outside the request/transaction when a worker is running."""
    from .push_notifications import send_push_to_user

    send_push_to_user(user_id, title, body, order_id, event_type)
