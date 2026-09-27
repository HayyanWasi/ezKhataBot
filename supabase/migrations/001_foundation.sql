-- ============================================================================
-- EzKhata 001 - Foundation
-- Users, businesses, employees, conversations, messages, preferences, memories.
-- Money tables are added per feature (002+).
-- Run once in Supabase SQL Editor. Everything runs in one transaction.
-- ============================================================================

begin;

-- ---------------------------------------------------------------------------
-- users: one row per person, identified by WhatsApp phone (923001234567)
-- ---------------------------------------------------------------------------
create table public.users (
    id          uuid primary key default gen_random_uuid(),
    phone       text not null unique check (phone ~ '^[0-9]{10,15}$'),
    name        text not null check (length(trim(name)) > 0),
    created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- businesses: a shop; one owner, an owner can have many
-- ---------------------------------------------------------------------------
create table public.businesses (
    id          uuid primary key default gen_random_uuid(),
    owner_id    uuid not null references public.users(id),
    name        text not null check (length(trim(name)) > 0),
    timezone    text not null default 'Asia/Karachi',
    created_at  timestamptz not null default now()
);
create index businesses_owner_idx on public.businesses(owner_id);

-- ---------------------------------------------------------------------------
-- business_employees: which employee can access which business
-- ---------------------------------------------------------------------------
create table public.business_employees (
    id           uuid primary key default gen_random_uuid(),
    business_id  uuid not null references public.businesses(id),
    user_id      uuid not null references public.users(id),
    status       text not null default 'active' check (status in ('active', 'removed')),
    added_by     uuid not null references public.users(id),
    created_at   timestamptz not null default now(),
    unique (business_id, user_id)
);
create index business_employees_user_idx on public.business_employees(user_id);

-- Access rule used everywhere: owner, or active employee
create function public.user_can_access_business(p_user_id uuid, p_business_id uuid)
returns boolean
language sql stable
as $$
    select exists (
        select 1 from public.businesses b
        where b.id = p_business_id and b.owner_id = p_user_id
    ) or exists (
        select 1 from public.business_employees e
        where e.business_id = p_business_id and e.user_id = p_user_id and e.status = 'active'
    );
$$;

-- ---------------------------------------------------------------------------
-- conversations: a user's chat with the bot on one channel,
-- plus the selected business and the single pending question
-- ---------------------------------------------------------------------------
create table public.conversations (
    id                   uuid primary key default gen_random_uuid(),
    user_id              uuid not null references public.users(id),
    channel              text not null check (channel in ('cli', 'whatsapp')),
    active_business_id   uuid references public.businesses(id),
    pending_action       jsonb,
    pending_question     text,
    pending_expires_at   timestamptz,
    created_at           timestamptz not null default now(),
    updated_at           timestamptz not null default now(),
    unique (user_id, channel),
    -- pending fields are set together or cleared together
    check (
        (pending_action is null and pending_question is null and pending_expires_at is null)
        or (pending_action is not null and pending_question is not null and pending_expires_at is not null)
    )
);

-- ---------------------------------------------------------------------------
-- messages: one row per message (user or bot)
--   user rows: external_id (provider message id) + processing state
--   bot rows : reply_to_id + delivery state
-- ---------------------------------------------------------------------------
create table public.messages (
    id                     uuid primary key default gen_random_uuid(),
    conversation_id        uuid not null references public.conversations(id),
    role                   text not null check (role in ('user', 'bot')),
    text                   text not null,
    business_id            uuid references public.businesses(id),
    intent                 text,
    created_at             timestamptz not null default now(),

    -- user rows
    external_id            text,
    processing_status      text check (processing_status in ('received', 'processed', 'failed', 'ignored')),
    processing_started_at  timestamptz,
    error                  text,

    -- bot rows
    reply_to_id            uuid references public.messages(id),
    delivery_status        text check (delivery_status in ('pending', 'sent', 'delivered', 'failed')),
    provider_message_id    text,
    send_attempts          integer not null default 0 check (send_attempts >= 0),
    last_send_error        text,
    sent_at                timestamptz,

    check (
        (role = 'user'
            and external_id is not null
            and processing_status is not null
            and reply_to_id is null
            and delivery_status is null)
        or
        (role = 'bot'
            and external_id is null
            and processing_status is null
            and delivery_status is not null)
    )
);

-- Duplicate protection: one row per provider message id per conversation
create unique index messages_external_id_uniq
    on public.messages(conversation_id, external_id)
    where role = 'user';

-- At most one reply per incoming message
create unique index messages_one_reply_uniq
    on public.messages(reply_to_id)
    where role = 'bot' and reply_to_id is not null;

-- Recent history for AI context
create index messages_conversation_created_idx
    on public.messages(conversation_id, created_at desc);

-- ---------------------------------------------------------------------------
-- user_preferences: language override (null = mirror user's language)
-- ---------------------------------------------------------------------------
create table public.user_preferences (
    user_id     uuid primary key references public.users(id),
    language    text check (language in ('en', 'ur', 'roman_ur')),
    updated_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- memories: saved only when the user explicitly asks; soft delete
-- ---------------------------------------------------------------------------
create table public.user_memories (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references public.users(id),
    content     text not null check (length(trim(content)) > 0),
    created_at  timestamptz not null default now(),
    deleted_at  timestamptz
);
create index user_memories_user_idx on public.user_memories(user_id) where deleted_at is null;

create table public.business_memories (
    id           uuid primary key default gen_random_uuid(),
    business_id  uuid not null references public.businesses(id),
    content      text not null check (length(trim(content)) > 0),
    created_by   uuid not null references public.users(id),
    created_at   timestamptz not null default now(),
    deleted_at   timestamptz
);
create index business_memories_business_idx on public.business_memories(business_id) where deleted_at is null;

-- ---------------------------------------------------------------------------
-- Row Level Security: on, with no policies.
-- Only the backend (direct Postgres connection) can read/write.
-- ---------------------------------------------------------------------------
alter table public.users              enable row level security;
alter table public.businesses         enable row level security;
alter table public.business_employees enable row level security;
alter table public.conversations      enable row level security;
alter table public.messages           enable row level security;
alter table public.user_preferences   enable row level security;
alter table public.user_memories      enable row level security;
alter table public.business_memories  enable row level security;

commit;
