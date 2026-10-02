"use client";

import { useParams, useRouter } from "next/navigation";
import { Loading, OnOff, PageTitle } from "@/components/ui";
import { phone, when } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Msg = {
  id: string; role: "user" | "bot"; text: string; intent: string | null; created_at: string;
  processing_status: string | null; delivery_status: string | null; error: string | null; file: boolean; shop: string | null;
};
type Chat = { user: { id: string; name: string; phone: string; disabled_at: string | null }; messages: Msg[] };

export default function ChatPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data, error, loading, reload } = useApi<Chat>(`/api/admin/chat/${id}?limit=500`);

  if (!data) return <Loading error={error} loading={loading} />;

  return (
    <>
      <button className="text-sm text-muted" onClick={() => router.back()}>← Wapas</button>
      <PageTitle title={data.user.name} sub={`${phone(data.user.phone)} · ${data.messages.length} messages`}
        right={<div className="flex gap-2 items-center"><OnOff off={data.user.disabled_at} /><button className="btn" onClick={reload}>↻</button></div>} />
      <div className="card p-3 sm:p-4 space-y-2 max-w-3xl">
        {data.messages.length === 0 && <div className="text-muted text-sm">Abhi koi baat nahi hui.</div>}
        {data.messages.map((m) => {
          const bad = m.intent === "unknown" || m.processing_status === "failed" || m.delivery_status === "failed";
          return (
            <div key={m.id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm ${m.role === "user" ? "bg-brand-soft" : "bg-bg border border-line"} ${bad ? "ring-2 ring-[var(--danger)]" : ""}`}>
                <div className="whitespace-pre-wrap break-words">{m.text}{m.file ? " 📎" : ""}</div>
                <div className="text-[11px] text-muted mt-1 flex gap-2 flex-wrap">
                  <span>{when(m.created_at)}</span>
                  {m.intent && <span>· {m.intent}</span>}
                  {m.shop && <span>· {m.shop}</span>}
                  {m.delivery_status && m.delivery_status !== "sent" && <span className="text-danger">· {m.delivery_status}</span>}
                  {m.error && <span className="text-danger">· {m.error.slice(0, 80)}</span>}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
