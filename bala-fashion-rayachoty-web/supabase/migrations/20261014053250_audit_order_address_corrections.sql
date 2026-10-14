create table if not exists public.order_address_audit (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders(id) on delete cascade,
  changed_by uuid not null references auth.users(id) on delete restrict,
  correction_reason text not null check (length(btrim(correction_reason)) > 0),
  previous_address jsonb not null,
  corrected_address jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists order_address_audit_order_created_idx
  on public.order_address_audit(order_id, created_at desc);
alter table public.order_address_audit enable row level security;
revoke all on public.order_address_audit from anon, authenticated;
comment on table public.order_address_audit is 'Private audit trail for administrator corrections to immutable order delivery addresses.';
