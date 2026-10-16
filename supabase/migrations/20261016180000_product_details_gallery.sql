-- Extended product copy and gallery images for the full product details page.
alter table public.products
  add column if not exists additional_description text not null default '';

create table if not exists public.product_images (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products(id) on delete cascade,
  image_url text not null check (image_url like 'https://res.cloudinary.com/%'),
  image_public_id text not null default '',
  alt_text text not null default '',
  sort_order integer not null default 0 check (sort_order >= 0),
  created_at timestamptz not null default now(),
  constraint product_images_product_sort_unique unique (product_id, sort_order)
);

create index if not exists product_images_product_sort_idx
  on public.product_images (product_id, sort_order, created_at);

alter table public.product_images enable row level security;
revoke all on table public.product_images from anon, authenticated;
grant all on table public.product_images to service_role;

comment on column public.products.additional_description is
  'Extended product details displayed on the full product details page.';
comment on table public.product_images is
  'Additional Cloudinary gallery images for products; accessed through the Django backend only.';
