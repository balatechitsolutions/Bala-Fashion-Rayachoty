begin;
alter table public.profiles
  add column if not exists is_active boolean not null default true,
  add column if not exists availability_status text not null default 'offline',
  add column if not exists latitude double precision,
  add column if not exists longitude double precision,
  add column if not exists last_location_at timestamptz;
alter table public.profiles drop constraint if exists profiles_availability_status_check;
alter table public.profiles add constraint profiles_availability_status_check
  check (availability_status in ('available','busy','offline'));
create index if not exists delivery_staff_available_idx
  on public.profiles (availability_status, last_location_at desc)
  where role='delivery_boy' and is_active=true;
create table if not exists public.delivery_assignment_notifications (
  id uuid primary key default gen_random_uuid(),
  recipient_id uuid not null references auth.users(id) on delete cascade,
  order_id uuid not null references public.orders(id) on delete cascade,
  order_number text not null,
  message text not null,
  read_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists delivery_assignment_notifications_recipient_idx
  on public.delivery_assignment_notifications(recipient_id, created_at desc);
update public.profiles set availability_status='offline' where role='delivery_boy';
commit;