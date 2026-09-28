-- ============================================================================
-- EzKhata 005 - Cash book, expenses, banks
-- Cash and banks are accounts too (one khata_entries row = one leg):
--   cash / bank amount > 0 = money came in, < 0 = money went out.
-- "Ali ne 1000 wapas diye" = one transaction, two legs: Ali -1000, Cash +1000.
-- Expense categories belong to each shop; category_words remembers which
-- word ("bijli") goes to which category, so the bot asks only once.
-- Run once in Supabase SQL Editor after 004. Everything runs in one transaction.
-- ============================================================================

begin;

-- ---------------------------------------------------------------------------
-- accounts: add cash (one per shop) and banks/wallets (name, optional number)
-- ---------------------------------------------------------------------------
alter table public.accounts drop constraint accounts_type_check;
alter table public.accounts add constraint accounts_type_check
    check (type in ('customer', 'supplier', 'cash', 'bank'));
alter table public.accounts add column account_number text;

create unique index accounts_one_cash_uniq
    on public.accounts(business_id) where type = 'cash' and deleted_at is null;

-- ---------------------------------------------------------------------------
-- expense_categories: each shop makes its own (Rent, Bijli, Chai ...)
-- ---------------------------------------------------------------------------
create table public.expense_categories (
    id           uuid primary key default gen_random_uuid(),
    business_id  uuid not null references public.businesses(id),
    name         text not null check (length(trim(name)) > 0),
    created_by   uuid not null references public.users(id),
    created_at   timestamptz not null default now(),
    deleted_at   timestamptz
);
create unique index expense_categories_name_uniq
    on public.expense_categories(business_id, lower(name)) where deleted_at is null;

-- A word the shopkeeper used once ("bijli") -> the category they picked for it
create table public.category_words (
    business_id  uuid not null references public.businesses(id),
    word         text not null check (word = lower(trim(word)) and length(word) > 0),
    category_id  uuid not null references public.expense_categories(id),
    created_at   timestamptz not null default now(),
    primary key (business_id, word)
);

-- ---------------------------------------------------------------------------
-- business_transactions: cash types, category, edit history
-- ---------------------------------------------------------------------------
alter table public.business_transactions drop constraint business_transactions_transaction_type_check;
alter table public.business_transactions add constraint business_transactions_transaction_type_check
    check (transaction_type in (
        'gave', 'got', 'opening_balance',
        'cash_in', 'cash_out', 'sale', 'transfer', 'adjustment'
    ));
alter table public.business_transactions
    add column category_id uuid references public.expense_categories(id),
    add column edited_from uuid references public.business_transactions(id);

-- ---------------------------------------------------------------------------
-- Row Level Security: on, with no policies (backend-only access, like 001)
-- ---------------------------------------------------------------------------
alter table public.expense_categories  enable row level security;
alter table public.category_words      enable row level security;

commit;
