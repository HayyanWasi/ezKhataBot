"use client";

import Link from "next/link";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";

const FIELDS = [
  { key: "name", label: "Aap ka naam", placeholder: "Ali Raza", type: "text" },
  { key: "phone", label: "WhatsApp number", placeholder: "03001234567", type: "tel" },
  { key: "shop_name", label: "Dukaan ka naam", placeholder: "Ali General Store", type: "text" },
  { key: "username", label: "Username", placeholder: "alistore (chhote harf, number)", type: "text" },
  { key: "password", label: "Password", placeholder: "kam az kam 6 harf", type: "password" },
] as const;

type Form = Record<(typeof FIELDS)[number]["key"] | "website", string>;

export default function Signup() {
  const [form, setForm] = useState<Form>({ name: "", phone: "", shop_name: "", username: "", password: "", website: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api<{ message?: string }>("/api/signup", { method: "POST", body: form, auth: false });
      setDone(res.message || "Shukriya! Request mil gayi.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Kuch ghalat ho gaya.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex-1 flex items-center justify-center px-4 py-12">
      <div className="card w-full max-w-md p-6 sm:p-8">
        <Link href="/" className="text-sm text-muted">← EzKhata</Link>
        <h1 className="text-2xl font-bold mt-2 mb-1">Apna EzKhata bot lein</h1>
        <p className="text-muted text-sm mb-6">Form bharein. Approve hote hi aap ke WhatsApp par bot chal jaega.</p>

        {done ? (
          <div className="rounded-xl bg-brand-soft p-4 text-brand font-medium">✅ {done}</div>
        ) : (
          <form onSubmit={submit} className="space-y-4">
            {FIELDS.map((f) => (
              <label key={f.key} className="block">
                <span className="text-sm font-medium">{f.label}</span>
                <input
                  className="input mt-1"
                  type={f.type}
                  required
                  placeholder={f.placeholder}
                  value={form[f.key]}
                  onChange={(e) => setForm({ ...form, [f.key]: f.key === "username" ? e.target.value.toLowerCase() : e.target.value })}
                  autoComplete={f.key === "password" ? "new-password" : f.key === "username" ? "username" : "off"}
                />
              </label>
            ))}
            {/* Hidden from people; spam bots fill it in */}
            <input type="text" tabIndex={-1} autoComplete="off" className="hidden" aria-hidden="true"
              value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} />
            {error && <p className="text-sm text-danger">{error}</p>}
            <button className="btn btn-brand w-full py-3" disabled={busy}>{busy ? "Bhej rahe hain…" : "Request bhejein"}</button>
          </form>
        )}
      </div>
    </main>
  );
}
