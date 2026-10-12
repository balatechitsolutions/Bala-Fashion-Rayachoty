-- Run once in Supabase SQL Editor before deploying the delivery-role backend.
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
