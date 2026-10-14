CREATE TABLE IF NOT EXISTS public.account_notifications (
    id uuid PRIMARY KEY,
    recipient_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    event_type text NOT NULL CHECK (event_type IN ('placed', 'delivered')),
    title text NOT NULL,
    body text NOT NULL,
    order_id uuid NOT NULL REFERENCES public.orders(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    read_at timestamptz NULL,
    CONSTRAINT account_notifications_one_event_per_recipient
        UNIQUE (recipient_id, order_id, event_type)
);
CREATE INDEX IF NOT EXISTS account_notifications_recipient_created_idx
    ON public.account_notifications (recipient_id, created_at DESC);
CREATE INDEX IF NOT EXISTS account_notifications_unread_idx
    ON public.account_notifications (recipient_id)
    WHERE read_at IS NULL;
