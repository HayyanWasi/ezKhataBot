"use client";

import Link from "next/link";
import { useState } from "react";
import { Empty, Loading, PageTitle } from "@/components/ui";
import { phone, when } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Problem = {
  id: string; created_at: string; text: string; intent: string | null; error: string | null;
  kind: "not_understood" | "error" | "undelivered"; user_id: string; user_name: string; phone: string; shop: string | null;
};

const KINDS = {
  not_understood: { label: "Nahi samjha", cls: "bg-warn-soft text-warn" },
  error: { label: "Error", cls: "bg-danger-soft text-danger" },
  undelivered: { label: "Jawab nahi pohncha", cls: "bg-danger-soft text-danger" },
} as const;

export default function ProblemsPage() {
  const [days, setDays] = useState(7);
  const [kind, setKind] = useState<string>("all");
  const { data, error, loading, reload } = useApi<Problem[]>(`/api/admin/problems?days=${days}`);
  const rows = (data || []).filter((p) => kind === "all" || p.kind === kind);

  return (
    <>
      <PageTitle title="Masle" sub="Jo messages bot nahi samjha, jahan error aaya, ya jawab nahi pohncha. Click karke poori chat dekhein."
        right={<button className="btn" onClick={reload}>↻ Refresh</button>} />
      <div className="flex gap-2 mb-4 flex-wrap">
        {[["all", "Sab"], ["not_understood", "Nahi samjha"], ["error", "Errors"], ["undelivered", "Nahi pohncha"]].map(([k, l]) => (
          <button key={k} className={`btn ${kind === k ? "btn-brand" : ""}`} onClick={() => setKind(k)}>{l}</button>
        ))}
        <select className="input w-auto" value={days} onChange={(e) => setDays(Number(e.target.value))}>
          <option value={1}>Aaj / 1 din</option><option value={7}>7 din</option><option value={30}>30 din</option>
        </select>
      </div>
      <Loading error={error} loading={loading && !data} />
      {data && rows.length === 0 && <Empty text="Koi masla nahi 🎉" />}
      {rows.length > 0 && (
        <div className="space-y-2">
          {rows.map((p) => (
            <Link key={p.id} href={`/admin/chat/${p.user_id}`} className="card p-3 flex gap-3 items-start hover:border-[var(--brand)]">
              <span className={`badge ${KINDS[p.kind].cls}`}>{KINDS[p.kind].label}</span>
              <div className="min-w-0 flex-1">
                <div className="text-sm whitespace-pre-wrap break-words">“{p.text}”</div>
                <div className="text-xs text-muted mt-1">{p.user_name} · {phone(p.phone)}{p.shop ? ` · ${p.shop}` : ""} · {when(p.created_at)}</div>
                {p.error && <div className="text-xs text-danger mt-1">{p.error.slice(0, 160)}</div>}
              </div>
            </Link>
          ))}
        </div>
      )}
    </>
  );
}
