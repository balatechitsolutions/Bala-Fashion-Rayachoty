begin;
alter table public.delivery_assignment_notifications enable row level security;
revoke all on public.delivery_assignment_notifications from anon, authenticated;
create index if not exists delivery_assignment_notifications_order_idx
  on public.delivery_assignment_notifications(order_id);
create index if not exists order_address_audit_changed_by_idx
  on public.order_address_audit(changed_by);
commit;
