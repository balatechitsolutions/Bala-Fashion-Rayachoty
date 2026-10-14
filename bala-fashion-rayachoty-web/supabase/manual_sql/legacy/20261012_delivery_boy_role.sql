-- ARCHIVED LEGACY MANUAL SCRIPT — NOT A SUPABASE MIGRATION.
-- This file was previously stored under supabase/migrations but has no matching
-- version in public.supabase_migrations.schema_migrations. Do not run it as part
-- of the canonical migration history. The current schema.sql baseline already
-- defines the delivery_boy role, assigned_delivery_boy_id, and the assignment
-- index. Retained here only for historical reference.
--
-- Original content:
begin;

alter table public.profiles drop constraint if exists profiles_role_check;
alter table public.profiles add constraint profiles_role_check
  check (role in ('customer', 'vendor', 'admin', 'delivery_boy'));

alter table public.orders
  add column if not exists assigned_delivery_boy_id uuid
  references auth.users(id) on delete set null;

create index if not exists orders_delivery_assignment_idx
  on public.orders (assigned_delivery_boy_id, status, created_at desc);

commit;
