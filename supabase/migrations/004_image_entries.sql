-- ============================================================================
-- EzKhata 004 - Image entries
-- One confirmed photo ("haan") can save several rows, so the duplicate guard
-- on business_transactions becomes (source_message_id, source_line).
-- User photo messages reuse messages.attachment_path (added in 003).
-- Run once in Supabase SQL Editor after 003. Everything runs in one transaction.
-- ============================================================================

begin;

alter table public.business_transactions add column source_line smallint not null default 0;

drop index public.business_transactions_source_message_uniq;
create unique index business_transactions_source_uniq
    on public.business_transactions(source_message_id, source_line) where source_message_id is not null;

commit;
