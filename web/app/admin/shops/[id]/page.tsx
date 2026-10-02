"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Loading, OnOff, PageTitle } from "@/components/ui";
import { api, ApiError, phone, when } from "@/lib/api";
import { useApi } from "@/lib/useApi";

type Person = { id: string; name: string; phone: string; disabled_at: string | null; status: string; created_at: string };
type ShopDetail = {
  id: string; name: string; created_at: string; disabled_at: string | null; address: string | null; shop_phone: string | null;
  owner_id: string; owner_name: string; owner_phone: string; owner_username: string | null; owner_disabled_at: string | null;
  employees: Person[];
};

export default function ShopPage() {
  const { id } = useParams<{ id: string }>();
  const { data: shop, error, loading, reload } = useApi<ShopDetail>(`/api/admin/shops/${id}`);
  const [msg, setMsg] = useState("");
  const [staff, setStaff] = useState({ name: "", phone: "" });

  async function act(path: string, method: string, body?: unknown, done?: string, ask?: string) {
    if (ask && !confirm(ask)) return;
    setMsg("");
    try {
      await api(path, { method, body });
      if (done) setMsg(done);
      reload();
    } catch (err) {
      setMsg(err instanceof ApiError ? err.message : "Kuch ghalat ho gaya.");
    }
  }

  if (!shop) return <Loading error={error} loading={loading} />;
  const active = shop.employees.filter((e) => e.status === "active");

  return (
    <>
      <Link href="/admin/shops" className="text-sm text-muted">← Dukaanen</Link>
      <PageTitle title={shop.name} sub={`Bani: ${when(shop.created_at)}${shop.address ? ` · ${shop.address}` : ""}`}
        right={<div className="flex items-center gap-2"><OnOff off={shop.disabled_at} />
          {shop.disabled_at
            ? <button className="btn btn-brand" onClick={() => act(`/api/admin/shops/${id}/enable`, "POST", undefined, "✅ Dukaan chalu ho gayi.")}>Bot chalu karein</button>
            : <button className="btn btn-danger" onClick={() => act(`/api/admin/shops/${id}/disable`, "POST", undefined, "Dukaan band ho gayi. Bot is dukaan par chup rahega.", `${shop.name} band karein? Malik aur employees ko bot jawab nahi dega.`)}>Dukaan band karein</button>}
        </div>} />
      {msg && <div className="card p-3 mb-4 text-sm">{msg}</div>}

      <div className="grid md:grid-cols-2 gap-4">
        <div className="card p-4">
          <div className="text-sm text-muted mb-2">Malik</div>
          <div className="font-semibold">{shop.owner_name}</div>
          <div className="text-sm text-muted">{phone(shop.owner_phone)}{shop.owner_username ? ` · @${shop.owner_username}` : ""}</div>
          <div className="flex gap-2 mt-3 flex-wrap items-center">
            <OnOff off={shop.owner_disabled_at} />
            <Link className="btn" href={`/admin/chat/${shop.owner_id}`}>💬 Chat dekhein</Link>
            {shop.owner_disabled_at
              ? <button className="btn" onClick={() => act(`/api/admin/users/${shop.owner_id}/enable`, "POST", undefined, "Number chalu.")}>Number chalu</button>
              : <button className="btn btn-danger" onClick={() => act(`/api/admin/users/${shop.owner_id}/disable`, "POST", undefined, "Number band.", "Is number par bot band karein?")}>Number band</button>}
          </div>
        </div>

        <div className="card p-4">
          <div className="text-sm text-muted mb-2">Employees ({active.length})</div>
          {shop.employees.length === 0 && <div className="text-sm text-muted">Koi employee nahi.</div>}
          <ul className="space-y-2">
            {shop.employees.map((e) => (
              <li key={e.id} className="flex items-center gap-2 flex-wrap">
                <div className="min-w-0 flex-1">
                  <span className={e.status === "active" ? "font-medium" : "line-through text-muted"}>{e.name}</span>
                  <span className="text-xs text-muted"> · {phone(e.phone)}</span>
                </div>
                <Link className="text-sm text-brand" href={`/admin/chat/${e.id}`}>chat</Link>
                {e.status === "active" && (
                  <button className="text-sm text-danger" onClick={() => act(`/api/admin/shops/${id}/employees/${e.id}`, "DELETE", undefined, `${e.name} hata diya.`, `${e.name} ko is dukaan se hatayein?`)}>hatayein</button>
                )}
              </li>
            ))}
          </ul>
          <form className="flex gap-2 mt-4 flex-wrap" onSubmit={(ev) => {
            ev.preventDefault();
            act(`/api/admin/shops/${id}/employees`, "POST", staff, `✅ ${staff.name} add ho gaya.`);
            setStaff({ name: "", phone: "" });
          }}>
            <input className="input flex-1 min-w-32" required placeholder="Naam" value={staff.name} onChange={(e) => setStaff({ ...staff, name: e.target.value })} />
            <input className="input flex-1 min-w-32" required placeholder="03001234567" value={staff.phone} onChange={(e) => setStaff({ ...staff, phone: e.target.value })} />
            <button className="btn btn-brand">+ Employee</button>
          </form>
        </div>
      </div>
    </>
  );
}
