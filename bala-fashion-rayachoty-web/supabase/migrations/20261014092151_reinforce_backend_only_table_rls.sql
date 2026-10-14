DO $$
DECLARE
  t text;
  backend_only_tables text[] := ARRAY[
    'account_notifications',
    'auth_group',
    'auth_group_permissions',
    'auth_permission',
    'auth_user',
    'auth_user_groups',
    'auth_user_user_permissions',
    'delivery_assignment_notifications',
    'django_admin_log',
    'django_content_type',
    'django_migrations',
    'django_session',
    'order_address_audit',
    'push_notification_devices'
  ];
BEGIN
  FOREACH t IN ARRAY backend_only_tables LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    IF NOT EXISTS (
      SELECT 1
      FROM pg_policies
      WHERE schemaname = 'public'
        AND tablename = t
        AND policyname = 'deny_client_access_backend_only'
    ) THEN
      EXECUTE format(
        'CREATE POLICY deny_client_access_backend_only ON public.%I AS RESTRICTIVE FOR ALL TO anon, authenticated USING (false) WITH CHECK (false)',
        t
      );
    END IF;
  END LOOP;
END
$$;
