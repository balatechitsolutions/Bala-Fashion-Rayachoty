-- Keep assignment notification rows available only to the trusted Django backend (service role).
alter table public.delivery_assignment_notifications enable row level security;
revoke all on table public.delivery_assignment_notifications from anon, authenticated;
grant all on table public.delivery_assignment_notifications to service_role;

-- Back the order lifecycle and notification joins with indexes.
create index if not exists account_notifications_order_id_idx on public.account_notifications(order_id);
create index if not exists delivery_assignment_notifications_order_id_idx on public.delivery_assignment_notifications(order_id);
create index if not exists order_address_audit_changed_by_idx on public.order_address_audit(changed_by);

-- Avoid retaining the duplicate one-default-address index; keep the migration-owned canonical name.
drop index if exists public.customer_addresses_one_default_idx;
