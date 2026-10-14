ALTER TABLE public.account_notifications ENABLE ROW LEVEL SECURITY; REVOKE ALL ON TABLE public.account_notifications FROM PUBLIC, anon, authenticated, service_role;
