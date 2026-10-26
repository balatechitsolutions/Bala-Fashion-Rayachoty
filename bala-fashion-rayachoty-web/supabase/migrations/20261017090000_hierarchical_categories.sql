-- Add optional parent categories while preserving all existing category/product IDs.
alter table public.categories
  add column if not exists parent_id uuid null references public.categories(id) on delete set null;

create index if not exists categories_parent_sort_idx
  on public.categories(parent_id, sort_order, name);

-- Prevent direct self-parenting. Deeper cycles are also rejected by the API.
alter table public.categories
  drop constraint if exists categories_not_own_parent,
  add constraint categories_not_own_parent check (parent_id is null or parent_id <> id);
