"use client";

import { useState } from "react";
import { Empty, Loading, PageTitle } from "@/components/ui";
import { api, ApiError, phone, when } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Req = { id: string; name: string; phone: string; shop_name: string; username: string; status: string; note: string | null; created_at: string; decided_at: string | null };

const TABS = [["pending", "Pending"], ["approved", "Approved"], ["rejected", "Rejected"], ["all", "Sab"]] as const;

export default function RequestsPage() {
  const [tab, setTab] = useState<string>("pending");
  const { data, error, loading, reload } = useApi<Req[]>(`/api/admin/requests?status=${tab}`);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");

  async function decide(r: Req, action: "approve" | "reject") {
    if (action === "reject" && !confirm(`${r.name} ki request reject karein?`)) return;
    setBusy(r.id);
    setMsg("");
    try {
      await api(`/api/admin/requests/${r.id}/${action}`, { method: "POST", body: {} });
      setMsg(action === "approve" ? `✅ ${r.name} approve ho gaya. Ab ${phone(r.phone)} par bot chalega.` : `${r.name} ki request reject ho gayi.`);
      reload();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Kuch ghalat ho gaya.");
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <PageTitle title="Signup requests" sub="Approve karte hi us number par bot chal jata hai" />
      <div className="flex gap-2 mb-4 flex-wrap">
        {TABS.map(([key, label]) => (
          <button key={key} onClick={() => setTab(key)} className={`btn ${tab === key ? "btn-brand" : ""}`}>{label}</button>
        ))}
      </div>
      {msg && <div className="card p-3 mb-4 text-sm">{msg}</div>}
      <Loading error={error} loading={loading && !data} />
      {data && data.length === 0 && <Empty text="Koi request nahi." />}
      {data && data.length > 0 && (
        <div className="space-y-3">
          {data.map((r) => (
            <div key={r.id} className="card p-4 flex flex-wrap items-center gap-4 justify-between">
              <div className="min-w-0">
                <div className="font-semibold">{r.shop_name}</div>
                <div className="text-sm text-muted">{r.name} · {phone(r.phone)} · @{r.username}</div>
                <div className="text-xs text-muted mt-1">Aayi: {when(r.created_at)}{r.decided_at ? ` · Faisla: ${when(r.decided_at)}` : ""}</div>
              </div>
              {r.status === "pending" ? (
                <div className="flex gap-2">
                  <button className="btn btn-brand" disabled={busy === r.id} onClick={() => decide(r, "approve")}>Approve</button>
                  <button className="btn btn-danger" disabled={busy === r.id} onClick={() => decide(r, "reject")}>Reject</button>
                </div>
              ) : (
                <span className={`badge ${r.status === "approved" ? "bg-brand-soft text-brand" : "bg-danger-soft text-danger"}`}>{r.status}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
