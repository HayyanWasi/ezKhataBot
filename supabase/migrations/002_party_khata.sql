-- ============================================================================
-- EzKhata 002 - Party khata
-- accounts (customers, suppliers; cash/bank come in Feature 3),
-- business_transactions (one money event) and khata_entries (its effect on an account).
-- Run once in Supabase SQL Editor after 001. Everything runs in one transaction.
-- ============================================================================

begin;

-- ---------------------------------------------------------------------------
-- accounts: anything that has a balance. Feature 1: customer, supplier.
-- ---------------------------------------------------------------------------
create table public.accounts (
    id           uuid primary key default gen_random_uuid(),
    business_id  uuid not null references public.businesses(id),
    type         text not null check (type in ('customer', 'supplier')),
    name         text not null check (length(trim(name)) > 0),
    phone        text check (phone ~ '^[0-9]{10,15}$'),
    created_by   uuid not null references public.users(id),
    created_at   timestamptz not null default now(),
    deleted_at   timestamptz
);
-- No two live accounts of the same type with the same name in one shop
create unique index accounts_name_uniq
    on public.accounts(business_id, type, lower(name)) where deleted_at is null;

-- ---------------------------------------------------------------------------
-- business_transactions: one money event (kept minimal; details live in entries)
-- ---------------------------------------------------------------------------
create table public.business_transactions (
    id                 uuid primary key default gen_random_uuid(),
    business_id        uuid not null references public.businesses(id),
    transaction_date   date not null,
    transaction_type   text not null check (transaction_type in ('gave', 'got', 'opening_balance')),
    reference_type     text,          -- e.g. 'bill' in Feature 4
    reference_id       uuid,
    source_message_id  uuid references public.messages(id),
    created_by         uuid not null references public.users(id),
    created_at         timestamptz not null default now(),
    deleted_at         timestamptz,
    deleted_by         uuid references public.users(id),
    check ((deleted_at is null) = (deleted_by is null))
);
-- Second duplicate guard: one incoming message creates at most one transaction
create unique index business_transactions_source_message_uniq
    on public.business_transactions(source_message_id) where source_message_id is not null;
create index business_transactions_business_created_idx
    on public.business_transactions(business_id, created_at desc);

-- ---------------------------------------------------------------------------
-- khata_entries: how a transaction changes an account's balance.
--   amount > 0  = you will get  (maine diye)
--   amount < 0  = you will give (maine liye)
-- ---------------------------------------------------------------------------
create table public.khata_entries (
    id              uuid primary key default gen_random_uuid(),
    transaction_id  uuid not null references public.business_transactions(id),
    account_id      uuid not null references public.accounts(id),
    amount          numeric(14, 2) not null check (amount <> 0),
    notes           text
);
create index khata_entries_account_idx on public.khata_entries(account_id);
create index khata_entries_transaction_idx on public.khata_entries(transaction_id);

-- ---------------------------------------------------------------------------
-- Row Level Security: on, with no policies (backend-only access, like 001)
-- ---------------------------------------------------------------------------
alter table public.accounts               enable row level security;
alter table public.business_transactions  enable row level security;
alter table public.khata_entries          enable row level security;

commit;
