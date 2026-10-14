BEGIN;
-- Authenticated users may edit contact fields only. Role, active status,
-- delivery availability, and live-location fields remain backend/admin managed.
REVOKE INSERT, UPDATE ON TABLE public.profiles FROM authenticated;
GRANT INSERT (id, full_name, phone) ON TABLE public.profiles TO authenticated;
GRANT UPDATE (full_name, phone) ON TABLE public.profiles TO authenticated;
COMMIT;
