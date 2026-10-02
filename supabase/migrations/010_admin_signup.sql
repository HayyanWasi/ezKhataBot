-- 010: signup requests + admin controls
--   * signup_requests: a shopkeeper fills in the signup page; the admin approves, then the bot works for that number
--   * users.username / password_hash: the shopkeeper's login (for the customer dashboard later)
--   * users.disabled_at / businesses.disabled_at: the admin turns the bot off for a number or a shop
-- Passwords are stored only as hashes (pbkdf2), never as typed.

begin;

alter table public.users
    add column username      text,
    add column password_hash text,
    add column disabled_at   timestamptz;
create unique index users_username_key on public.users (lower(username)) where username is not null;

alter table public.businesses
    add column disabled_at timestamptz;

create table public.signup_requests (
    id            uuid primary key default gen_random_uuid(),
    name          text not null check (length(trim(name)) between 1 and 80),
    phone         text not null check (phone ~ '^[0-9]{10,15}$'),
    shop_name     text not null check (length(trim(shop_name)) between 1 and 80),
    username      text not null check (username ~ '^[a-z0-9_.]{3,30}$'),
    password_hash text not null,
    status        text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
    note          text,
    user_id       uuid references public.users(id),  -- set on approval
    created_at    timestamptz not null default now(),
    decided_at    timestamptz
);
-- one open request per number / username
create unique index signup_requests_pending_phone on public.signup_requests (phone) where status = 'pending';
create unique index signup_requests_pending_username on public.signup_requests (lower(username)) where status = 'pending';
create index signup_requests_status_idx on public.signup_requests (status, created_at desc);

alter table public.signup_requests enable row level security;
revoke all on public.signup_requests from anon, authenticated;

commit;
