-- 009: chat_log, every WhatsApp / CLI message with the person's name and number, for reading chats
-- in Supabase's Table Editor (filter by naam or number). A view: nothing is copied, it reads `messages`.
-- Only the database owner can read it; Supabase's public API roles (anon, authenticated) cannot.

begin;

create or replace view public.chat_log
with (security_invoker = true)  -- reads the tables with the caller's rights (their RLS still applies)
as
select
    m.created_at at time zone 'Asia/Karachi' as waqt,
    u.phone                                  as number,
    u.name                                   as naam,
    b.name                                   as dukaan,
    case m.role when 'user' then '👤 ' || u.name else '🤖 Bot' end as kaun,
    m.text                                   as message,
    m.intent                                 as bot_ne_samjha,
    case when m.role = 'user' then m.processing_status else m.delivery_status end as status,
    coalesce(m.error, m.last_send_error)     as error,
    m.attachment_path is not null            as file,
    c.channel,
    m.conversation_id,
    m.id                                     as message_id
from messages m
join conversations c on c.id = m.conversation_id
join users u on u.id = c.user_id
left join businesses b on b.id = m.business_id
order by m.created_at desc;

revoke all on public.chat_log from anon, authenticated;

commit;
