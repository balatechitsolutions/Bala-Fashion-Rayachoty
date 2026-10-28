-- Bala Mart: category-aware vendor onboarding and legal document metadata.
-- Files are stored in Cloudinary; private access should be configured for the folder and
-- the backend API only returns document metadata to administrators.
create table if not exists public.vendor_categories (
  vendor_id uuid not null references public.vendors(id) on delete cascade,
  category_id uuid not null references public.categories(id) on delete restrict,
  created_at timestamptz not null default now(),
  primary key (vendor_id, category_id)
);
create table if not exists public.vendor_legal_documents (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid not null references public.vendors(id) on delete cascade,
  document_type text not null check (document_type in ('identity_proof','business_proof','gst_certificate','fssai_license','drug_license','other_license')),
  file_name text not null,
  file_url text not null,
  public_id text not null default '',
  mime_type text not null,
  file_size bigint not null check (file_size > 0 and file_size <= 10485760),
  uploaded_at timestamptz not null default now(),
  uploaded_by uuid references auth.users(id) on delete set null
);
create index if not exists vendor_legal_documents_vendor_idx
  on public.vendor_legal_documents(vendor_id, uploaded_at desc);
create index if not exists vendor_categories_category_idx
  on public.vendor_categories(category_id, vendor_id);
alter table public.vendor_categories enable row level security;
alter table public.vendor_legal_documents enable row level security;
revoke all on public.vendor_categories from anon, authenticated;
revoke all on public.vendor_legal_documents from anon, authenticated;
