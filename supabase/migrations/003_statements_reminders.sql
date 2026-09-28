-- ============================================================================
-- EzKhata 003 - Statements + reminders
-- messages.attachment_path (PDF statements), reminders, reminder_sends.
-- Run once in Supabase SQL Editor after 002. Everything runs in one transaction.
-- ============================================================================

begin;

-- A bot message can carry a file (PDF statement); a duplicate resend re-sends the same file
alter table public.messages add column attachment_path text;

-- ---------------------------------------------------------------------------
-- reminders: something the user asked to be reminded about (sent to that user only)
-- ---------------------------------------------------------------------------
create table public.reminders (
    id                 uuid primary key default gen_random_uuid(),
    business_id        uuid not null references public.businesses(id),
    user_id            uuid not null references public.users(id),          -- who receives it
    conversation_id    uuid not null references public.conversations(id),  -- which chat / channel
    language           text not null check (language in ('en', 'ur', 'roman_ur')),
    text               text not null check (length(trim(text)) > 0),
    account_id         uuid references public.accounts(id),                -- optional linked party
    remind_date        date not null,
    remind_time        time,                                                -- null = day only
    source_message_id  uuid references public.messages(id),
    created_at         timestamptz not null default now(),
    cancelled_at       timestamptz
);
-- One reminder per incoming message (duplicate guard)
create unique index reminders_source_message_uniq
    on public.reminders(source_message_id) where source_message_id is not null;
create index reminders_user_idx on public.reminders(business_id, user_id) where cancelled_at is null;

-- ---------------------------------------------------------------------------
-- reminder_sends: each moment a reminder goes out (1 for a set time, 2 for a day)
--   pending   -> waiting for send_at
--   queued    -> bot message created (delivery tracked on messages.delivery_status)
--   cancelled -> user cancelled the reminder
-- ---------------------------------------------------------------------------
create table public.reminder_sends (
    id           uuid primary key default gen_random_uuid(),
    reminder_id  uuid not null references public.reminders(id),
    send_at      timestamptz not null,
    status       text not null default 'pending' check (status in ('pending', 'queued', 'cancelled')),
    message_id   uuid references public.messages(id),
    created_at   timestamptz not null default now(),
    unique (reminder_id, send_at),
    check ((status = 'queued') = (message_id is not null))
);
create index reminder_sends_due_idx on public.reminder_sends(send_at) where status = 'pending';

-- ---------------------------------------------------------------------------
-- Row Level Security: on, with no policies (backend-only access, like 001/002)
-- ---------------------------------------------------------------------------
alter table public.reminders       enable row level security;
alter table public.reminder_sends  enable row level security;

commit;
