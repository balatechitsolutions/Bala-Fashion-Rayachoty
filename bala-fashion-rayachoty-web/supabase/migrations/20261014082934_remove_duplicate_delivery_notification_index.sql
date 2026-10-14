-- Remove the redundant order_id index; delivery_assignment_notifications_order_id_idx
-- already covers the same column and preserves lookup performance.
DROP INDEX IF EXISTS public.delivery_assignment_notifications_order_idx;
