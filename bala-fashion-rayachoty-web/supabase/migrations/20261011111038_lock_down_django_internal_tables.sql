DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'django_migrations','django_content_type','auth_permission','auth_group',
    'auth_group_permissions','auth_user','auth_user_groups',
    'auth_user_user_permissions','django_admin_log','django_session'
  ]
  LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM anon, authenticated', t);
  END LOOP;
END
$$;
REVOKE ALL PRIVILEGES ON SEQUENCE public.auth_user_id_seq FROM anon, authenticated;
