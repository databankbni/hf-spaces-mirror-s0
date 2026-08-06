-- ===========================================================================
-- Auto-create a public.users profile row when someone signs up via Supabase Auth.
-- Apply after 0001_init.sql.
-- ===========================================================================

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.users (id, email, name, role)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'name', split_part(new.email, '@', 1)),
    'buyer'
  )
  on conflict (id) do nothing;
  return new;
end $$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- To make yourself an admin after signing in once:
--   update public.users set role = 'admin' where email = 'you@example.com';
