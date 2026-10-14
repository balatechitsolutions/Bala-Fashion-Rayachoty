-- Least-privilege grants applied to the live Supabase project as migration 20261014083904.
BEGIN;
REVOKE ALL PRIVILEGES ON TABLE
  public.categories,
  public.customer_addresses,
  public.order_items,
  public.orders,
  public.products,
  public.profiles,
  public.push_notification_devices,
  public.vendors
FROM anon, authenticated;

GRANT SELECT ON TABLE public.vendors, public.categories, public.products TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.profiles TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.customer_addresses TO authenticated;
GRANT SELECT ON TABLE public.orders, public.order_items TO authenticated;
COMMIT;
