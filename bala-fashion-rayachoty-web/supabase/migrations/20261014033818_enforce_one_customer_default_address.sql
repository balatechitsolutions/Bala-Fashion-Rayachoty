with ranked as (
  select id, user_id,
         row_number() over (
           partition by user_id
           order by is_default desc, updated_at desc nulls last, created_at desc, id
         ) as position
  from public.customer_addresses
)
update public.customer_addresses a
set is_default = (ranked.position = 1),
    updated_at = now()
from ranked
where ranked.id = a.id
  and a.is_default is distinct from (ranked.position = 1);

create unique index if not exists customer_addresses_one_default_per_user
  on public.customer_addresses (user_id)
  where is_default = true;

comment on index public.customer_addresses_one_default_per_user is
  'Enforces at most one default saved delivery address per customer.';
