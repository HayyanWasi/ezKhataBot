-- ============================================================================
-- EzKhata 006 - Stock book
-- Items belong to a shop. Every stock event (opening, stock in, purchase,
-- stock out) is one business_transactions row; its items are stock_moves rows
-- (qty > 0 came in, < 0 went out). A purchase also has money legs in
-- khata_entries (supplier / cash / bank), exactly like other transactions.
-- A move counts only while its transaction is live, so undo / delete / edit
-- (soft delete of the transaction) work for stock too.
-- item_words remembers a word the shopkeeper used ("jurab") -> the item.
-- Run once in Supabase SQL Editor after 005. Everything runs in one transaction.
-- ============================================================================

begin;

-- ---------------------------------------------------------------------------
-- items
-- ---------------------------------------------------------------------------
create table public.items (
    id                uuid primary key default gen_random_uuid(),
    business_id       uuid not null references public.businesses(id),
    name              text not null check (length(trim(name)) > 0),
    category          text,
    unit              text not null check (length(trim(unit)) > 0),
    sale_price        numeric(14,2) check (sale_price >= 0),
    purchase_price    numeric(14,2) check (purchase_price >= 0),
    barcode           text,
    photo_message_id  uuid references public.messages(id),
    low_stock_level   numeric(14,3) check (low_stock_level >= 0),
    created_by        uuid not null references public.users(id),
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    deleted_at        timestamptz
);
create unique index items_name_uniq
    on public.items(business_id, lower(name)) where deleted_at is null;
create unique index items_barcode_uniq
    on public.items(business_id, barcode) where deleted_at is null and barcode is not null;

-- A word the shopkeeper used once ("jurab") -> the item they meant (Socks)
create table public.item_words (
    business_id  uuid not null references public.businesses(id),
    word         text not null check (word = lower(trim(word)) and length(word) > 0),
    item_id      uuid not null references public.items(id),
    created_at   timestamptz not null default now(),
    primary key (business_id, word)
);

-- ---------------------------------------------------------------------------
-- stock_moves: one row per item of a stock event
-- ---------------------------------------------------------------------------
create table public.stock_moves (
    id              uuid primary key default gen_random_uuid(),
    transaction_id  uuid not null references public.business_transactions(id),
    item_id         uuid not null references public.items(id),
    qty             numeric(14,3) not null check (qty <> 0),
    rate            numeric(14,2) check (rate >= 0),
    line            int not null default 0
);
create index stock_moves_item_idx on public.stock_moves(item_id);
create index stock_moves_transaction_idx on public.stock_moves(transaction_id);

-- ---------------------------------------------------------------------------
-- business_transactions: stock types
-- ---------------------------------------------------------------------------
alter table public.business_transactions drop constraint business_transactions_transaction_type_check;
alter table public.business_transactions add constraint business_transactions_transaction_type_check
    check (transaction_type in (
        'gave', 'got', 'opening_balance',
        'cash_in', 'cash_out', 'sale', 'transfer', 'adjustment',
        'stock_opening', 'stock_in', 'stock_out', 'purchase'
    ));

-- ---------------------------------------------------------------------------
-- Row Level Security: on, with no policies (backend-only access, like 001)
-- ---------------------------------------------------------------------------
alter table public.items        enable row level security;
alter table public.item_words   enable row level security;
alter table public.stock_moves  enable row level security;

commit;
