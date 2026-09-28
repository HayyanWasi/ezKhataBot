-- ============================================================================
-- EzKhata 007 - Bills + counter sale
-- A bill is one business_transactions row (type 'bill'):
--   its items are stock_moves rows (qty < 0, rate = the sale rate),
--   its money legs are khata_entries (cash / bank +paid, customer +balance).
-- The bills row holds the bill number, customer and totals. A bill is
-- cancelled when its transaction is soft-deleted (stock, cash, khata come back).
-- The shop's address and phone are printed on every bill.
-- Run once in Supabase SQL Editor after 006. Everything runs in one transaction.
-- ============================================================================

begin;

alter table public.businesses
    add column address text,
    add column phone   text;

create table public.bills (
    id                uuid primary key default gen_random_uuid(),
    business_id       uuid not null references public.businesses(id),
    bill_no           int  not null check (bill_no > 0),
    transaction_id    uuid not null unique references public.business_transactions(id),
    customer_id       uuid references public.accounts(id),  -- null = walk-in
    customer_name     text not null,
    subtotal          numeric(14,2) not null check (subtotal >= 0),
    discount_amount   numeric(14,2) not null default 0 check (discount_amount >= 0),
    discount_percent  numeric(6,2) check (discount_percent >= 0),
    tax_amount        numeric(14,2) not null default 0 check (tax_amount >= 0),
    tax_percent       numeric(6,2) check (tax_percent >= 0),
    total             numeric(14,2) not null check (total >= 0),
    paid_amount       numeric(14,2) not null default 0 check (paid_amount >= 0),
    pay_via           text not null check (pay_via in ('cash', 'bank', 'unpaid')),
    created_by        uuid not null references public.users(id),
    created_at        timestamptz not null default now(),
    unique (business_id, bill_no)
);
create index bills_customer_idx on public.bills(customer_id);

alter table public.business_transactions drop constraint business_transactions_transaction_type_check;
alter table public.business_transactions add constraint business_transactions_transaction_type_check
    check (transaction_type in (
        'gave', 'got', 'opening_balance',
        'cash_in', 'cash_out', 'sale', 'transfer', 'adjustment',
        'stock_opening', 'stock_in', 'stock_out', 'purchase',
        'bill'
    ));

alter table public.bills enable row level security;

commit;
