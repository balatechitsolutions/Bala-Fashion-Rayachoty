-- Safe, repeatable repair of legacy order address snapshots.
-- Existing non-empty order values always win; missing fields are filled only
-- from the same customer's saved address. Unknown values remain missing and
-- must be supplied by the customer or corrected by an administrator.
with preferred_address as (
  select distinct on (user_id)
    user_id, recipient_name, phone, line1, line2, landmark, city, state,
    postal_code, latitude, longitude, id
  from public.customer_addresses
  order by user_id, is_default desc, updated_at desc nulls last, created_at desc
)
update public.orders o
set address_snapshot =
  coalesce(o.address_snapshot, '{}'::jsonb)
  || jsonb_strip_nulls(jsonb_build_object(
    'recipient_name', coalesce(nullif(btrim(o.address_snapshot->>'recipient_name'), ''), nullif(btrim(a.recipient_name), '')),
    'phone', coalesce(nullif(btrim(o.address_snapshot->>'phone'), ''), nullif(btrim(a.phone), '')),
    'line1', coalesce(nullif(btrim(o.address_snapshot->>'line1'), ''), nullif(btrim(a.line1), '')),
    'line2', coalesce(nullif(btrim(o.address_snapshot->>'line2'), ''), nullif(btrim(a.line2), '')),
    'landmark', coalesce(nullif(btrim(o.address_snapshot->>'landmark'), ''), nullif(btrim(a.landmark), '')),
    'city', coalesce(nullif(btrim(o.address_snapshot->>'city'), ''), nullif(btrim(a.city), 'Rayachoty'), 'Rayachoty'),
    'state', coalesce(nullif(btrim(o.address_snapshot->>'state'), ''), nullif(btrim(a.state), 'Andhra Pradesh'), 'Andhra Pradesh'),
    'postal_code', coalesce(nullif(btrim(o.address_snapshot->>'postal_code'), ''), nullif(btrim(a.postal_code), '')),
    'latitude', case when nullif(o.address_snapshot->>'latitude','') is null then to_jsonb(a.latitude) else o.address_snapshot->'latitude' end,
    'longitude', case when nullif(o.address_snapshot->>'longitude','') is null then to_jsonb(a.longitude) else o.address_snapshot->'longitude' end,
    'saved_address_id', coalesce(nullif(o.address_snapshot->>'saved_address_id', ''), a.id::text)
  )),
  updated_at = now()
from preferred_address a
where a.user_id = o.customer_id
  and (
    coalesce(nullif(btrim(o.address_snapshot->>'recipient_name'), ''), nullif(btrim(o.address_snapshot->>'phone'), ''),
      nullif(btrim(o.address_snapshot->>'line1'), ''), nullif(o.address_snapshot->>'latitude',''),
      nullif(o.address_snapshot->>'longitude','')) is null
    or nullif(btrim(o.address_snapshot->>'recipient_name'), '') is null
    or nullif(btrim(o.address_snapshot->>'phone'), '') is null
    or nullif(btrim(o.address_snapshot->>'line1'), '') is null
    or nullif(o.address_snapshot->>'latitude','') is null
    or nullif(o.address_snapshot->>'longitude','') is null
  );
