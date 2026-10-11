create or replace function public.protect_profile_role()
returns trigger
language plpgsql
security definer
set search_path = public, auth
as $$
begin
  if coalesce(auth.role(), '') = 'authenticated' then
    if tg_op = 'INSERT' and new.role <> 'customer' then
      raise exception 'New profiles must start as customer';
    end if;
    if tg_op = 'UPDATE' and new.role is distinct from old.role then
      raise exception 'Profile roles can only be changed by an administrator';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists protect_profile_role_before_write on public.profiles;
create trigger protect_profile_role_before_write
before insert or update on public.profiles
for each row execute function public.protect_profile_role();

create or replace function public.create_profile_for_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public, auth
as $$
begin
  insert into public.profiles (id, full_name, phone, role)
  values (
    new.id,
    coalesce(nullif(new.raw_user_meta_data->>'full_name', ''), nullif(new.raw_user_meta_data->>'name', ''), ''),
    coalesce(new.phone, ''),
    'customer'
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created_profile on auth.users;
create trigger on_auth_user_created_profile
after insert on auth.users
for each row execute function public.create_profile_for_auth_user();

insert into public.profiles (id, full_name, phone, role)
select
  u.id,
  coalesce(nullif(u.raw_user_meta_data->>'full_name', ''), nullif(u.raw_user_meta_data->>'name', ''), ''),
  coalesce(u.phone, ''),
  'customer'
from auth.users u
on conflict (id) do nothing;

update public.profiles p
set role = 'vendor',
    updated_at = now()
from public.vendors v
where v.owner_id = p.id
  and v.status = 'approved'
  and p.role = 'customer';
