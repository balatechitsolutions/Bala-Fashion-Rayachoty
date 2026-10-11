-- Lock down Django's internal auth/admin/session tables from PostgREST roles.
-- Django connects as the table owner (postgres), which bypasses RLS because FORCE ROW LEVEL SECURITY is intentionally not enabled.
-- No client policies are defined: anon/authenticated must not access these internal tables through the public API.
ALTER TABLE public.django_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.django_content_type ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auth_permission ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auth_group ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auth_group_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auth_user ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auth_user_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auth_user_user_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.django_admin_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.django_session ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE
  public.django_migrations,
  public.django_content_type,
  public.auth_permission,
  public.auth_group,
  public.auth_group_permissions,
  public.auth_user,
  public.auth_user_groups,
  public.auth_user_user_permissions,
  public.django_admin_log,
  public.django_session
FROM PUBLIC, anon, authenticated;
