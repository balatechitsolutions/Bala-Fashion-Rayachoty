begin;

create table if not exists public.customer_addresses (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  recipient_name text not null,
  phone text not null,
  line1 text not null,
  line2 text not null default '',
  landmark text not null default '',
  city text not null default 'Rayachoty',
  state text not null default 'Andhra Pradesh',
  postal_code text not null default '',
  latitude double precision not null,
  longitude double precision not null,
  notes text not null default '',
  is_default boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists customer_addresses_user_idx
  on public.customer_addresses(user_id, is_default desc, created_at desc);

create unique index if not exists customer_addresses_one_default_idx
  on public.customer_addresses(user_id) where is_default = true;

alter table public.orders
  add column if not exists delivery_otp_hash text,
  add column if not exists delivery_otp_expires_at timestamptz,
  add column if not exists delivery_otp_sent_at timestamptz,
  add column if not exists delivery_otp_attempts integer not null default 0;

commit;
