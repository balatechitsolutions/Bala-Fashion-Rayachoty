-- Apply in the Supabase SQL Editor during a low-traffic period.
-- CREATE INDEX CONCURRENTLY cannot run inside a transaction; these regular
-- idempotent indexes are suitable for the Supabase SQL editor.
CREATE INDEX IF NOT EXISTS idx_products_active_created_id
    ON public.products (created_at DESC, id DESC)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_products_category_active_created
    ON public.products (category_id, created_at DESC, id DESC)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_products_vendor_created
    ON public.products (vendor_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_vendors_status_id
    ON public.vendors (status, id);

CREATE INDEX IF NOT EXISTS idx_categories_active_sort_name
    ON public.categories (sort_order, name)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_orders_customer_created
    ON public.orders (customer_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_orders_vendor_created
    ON public.orders (vendor_id, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_orders_delivery_created
    ON public.orders (assigned_delivery_boy_id, created_at DESC, id DESC)
    WHERE assigned_delivery_boy_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_order_items_order_id
    ON public.order_items (order_id);

CREATE INDEX IF NOT EXISTS idx_profiles_role
    ON public.profiles (role);

CREATE INDEX IF NOT EXISTS idx_push_devices_user_id
    ON public.push_notification_devices (user_id);
