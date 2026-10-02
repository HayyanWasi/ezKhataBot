"use client";

import Link from "next/link";
import { useState } from "react";
import { Empty, Loading, OnOff, PageTitle } from "@/components/ui";
import { api, ApiError, phone, when } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Shop = {
  id: string; name: string; created_at: string; disabled_at: string | null;
  owner_id: string; owner_name: string; owner_phone: string; owner_disabled_at: string | null;
  employees: number; messages: number; last_active: string | null;
};

function AddShop({ onDone }: { onDone: () => void }) {
  const [form, setForm] = useState({ name: "", phone: "", shop_name: "" });
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/api/admin/shops", { method: "POST", body: form });
      setMsg(`✅ ${form.shop_name} ban gayi, bot chalu.`);
      setForm({ name: "", phone: "", shop_name: "" });
      onDone();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Kuch ghalat ho gaya.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card p-4 mb-5">
      <div className="font-semibold mb-3">Seedha dukaan add karein (bina signup)</div>
      <div className="grid sm:grid-cols-4 gap-2">
        <input className="input" required placeholder="Malik ka naam" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input className="input" required placeholder="WhatsApp 03001234567" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        <input className="input" required placeholder="Dukaan ka naam" value={form.shop_name} onChange={(e) => setForm({ ...form, shop_name: e.target.value })} />
        <button className="btn btn-brand" disabled={busy}>Add + bot chalu</button>
      </div>
      {msg && <p className="text-sm mt-2">{msg}</p>}
    </form>
  );
}

export default function ShopsPage() {
  const { data, error, loading, reload } = useApi<Shop[]>("/api/admin/shops");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);

  const query = q.trim().toLowerCase();
  const shops = (data || []).filter((s) =>
    !query || [s.name, s.owner_name, s.owner_phone].some((v) => v.toLowerCase().includes(query)));

  return (
    <>
      <PageTitle title="Dukaanen" sub={data ? `${data.length} dukaanen` : undefined}
        right={<button className="btn" onClick={() => setAdding(!adding)}>{adding ? "Band karein" : "+ Dukaan add"}</button>} />
      {adding && <AddShop onDone={reload} />}
      <input className="input mb-4 max-w-sm" placeholder="Dhoondein: dukaan, naam ya number" value={q} onChange={(e) => setQ(e.target.value)} />
      <Loading error={error} loading={loading && !data} />
      {data && shops.length === 0 && <Empty text="Koi dukaan nahi mili." />}
      {shops.length > 0 && (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-muted border-b border-line">
              <tr>
                <th className="p-3">Dukaan</th><th className="p-3">Malik</th><th className="p-3">Employees</th>
                <th className="p-3">Messages</th><th className="p-3">Aakhri baar</th><th className="p-3">Bot</th>
              </tr>
            </thead>
            <tbody>
              {shops.map((s) => (
                <tr key={s.id} className="border-b border-line last:border-0">
                  <td className="p-3"><Link className="font-semibold text-brand" href={`/admin/shops/${s.id}`}>{s.name}</Link>
                    <div className="text-xs text-muted">Bani: {when(s.created_at)}</div></td>
                  <td className="p-3">{s.owner_name}<div className="text-xs text-muted">{phone(s.owner_phone)}</div></td>
                  <td className="p-3 tabular-nums">{s.employees}</td>
                  <td className="p-3 tabular-nums">{s.messages}</td>
                  <td className="p-3 whitespace-nowrap">{when(s.last_active)}</td>
                  <td className="p-3"><OnOff off={s.disabled_at || s.owner_disabled_at} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
