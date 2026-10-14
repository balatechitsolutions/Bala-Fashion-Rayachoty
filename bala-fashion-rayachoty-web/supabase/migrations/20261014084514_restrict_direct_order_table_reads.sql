BEGIN;
-- Order reads must go through the Django API, which returns role-appropriate
-- fields and never exposes OTP hashes or delivery-verification internals.
REVOKE ALL PRIVILEGES ON TABLE public.orders, public.order_items FROM anon, authenticated;
COMMIT;
