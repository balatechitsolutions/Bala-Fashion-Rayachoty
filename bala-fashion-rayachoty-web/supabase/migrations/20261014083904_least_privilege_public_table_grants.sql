BEGIN;
-- Remove the accidental broad table-level grants on API-facing tables.
-- Regrant only the least privileges required by the documented client model.
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

-- Catalog is read-only from the public client; RLS restricts rows to active/approved records.
GRANT SELECT ON TABLE public.vendors, public.categories, public.products TO anon, authenticated;

-- Keep authenticated account/address capabilities as defined in the repository bootstrap.
GRANT SELECT, INSERT, UPDATE ON TABLE public.profiles TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.customer_addresses TO authenticated;
GRANT SELECT ON TABLE public.orders, public.order_items TO authenticated;

-- push_notification_devices is backend-managed; no direct client table grants.
COMMIT;
