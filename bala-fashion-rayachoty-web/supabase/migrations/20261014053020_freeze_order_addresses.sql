alter table public.orders
  add column if not exists vendor_name_snapshot text not null default '',
  add column if not exists vendor_phone_snapshot text not null default '',
  add column if not exists vendor_address_snapshot text not null default '',
  add column if not exists vendor_latitude_snapshot double precision,
  add column if not exists vendor_longitude_snapshot double precision;

update public.orders o
set vendor_name_snapshot = coalesce(nullif(o.vendor_name_snapshot, ''), v.name, ''),
    vendor_phone_snapshot = coalesce(nullif(o.vendor_phone_snapshot, ''), v.phone, ''),
    vendor_address_snapshot = coalesce(nullif(o.vendor_address_snapshot, ''), v.address, ''),
    vendor_latitude_snapshot = coalesce(o.vendor_latitude_snapshot, v.latitude),
    vendor_longitude_snapshot = coalesce(o.vendor_longitude_snapshot, v.longitude)
from public.vendors v
where v.id = o.vendor_id
  and (o.vendor_name_snapshot = ''
    or o.vendor_phone_snapshot = ''
    or o.vendor_address_snapshot = ''
    or o.vendor_latitude_snapshot is null
    or o.vendor_longitude_snapshot is null);

comment on column public.orders.address_snapshot is
  'Customer delivery address and map coordinates captured at checkout; never resolve from the live address book for an existing order.';
comment on column public.orders.vendor_name_snapshot is 'Vendor/store name captured when this order was placed.';
comment on column public.orders.vendor_phone_snapshot is 'Vendor contact phone captured when this order was placed.';
comment on column public.orders.vendor_address_snapshot is 'Vendor pickup address captured when this order was placed.';
comment on column public.orders.vendor_latitude_snapshot is 'Vendor pickup latitude captured when this order was placed.';
comment on column public.orders.vendor_longitude_snapshot is 'Vendor pickup longitude captured when this order was placed.';
