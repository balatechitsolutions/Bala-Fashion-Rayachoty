begin;
create table if not exists public.push_notification_devices (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  token text not null unique,
  platform text not null default 'web',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists push_notification_devices_user_idx
  on public.push_notification_devices(user_id, updated_at desc);
alter table public.push_notification_devices enable row level security;
commit;
