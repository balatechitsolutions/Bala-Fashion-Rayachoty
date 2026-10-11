-- Lock down Django's internal auth/admin tables exposed in the public schema.
-- Django connects as the table owner (postgres) on the backend; do not FORCE RLS.
-- PostgREST roles (anon/authenticated) receive no direct table privileges and no RLS policies.
BEGIN;

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'django_migrations',
    'django_content_type',
    'auth_permission',
    'auth_group',
    'auth_group_permissions',
    'auth_user',
    'auth_user_groups',
    'auth_user_user_permissions',
    'django_admin_log',
    'django_session'
  ]
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM anon, authenticated', t);
  END LOOP;
END
$$;

-- Django's serial auth_user ID sequence is also internal. Revoke client-role access
-- while retaining owner/backend access.
REVOKE ALL PRIVILEGES ON SEQUENCE public.auth_user_id_seq FROM anon, authenticated;

COMMIT;
