"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError, setToken } from "@/lib/api";

export default function Login() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api<{ token: string }>("/api/admin/login", { method: "POST", body: { username, password }, auth: false });
      setToken(res.token);
      router.replace("/admin");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Kuch ghalat ho gaya.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex-1 flex items-center justify-center px-4 py-12">
      <form onSubmit={submit} className="card w-full max-w-sm p-6 sm:p-8 space-y-4">
        <div>
          <h1 className="text-2xl font-bold">EzKhata Admin</h1>
          <p className="text-muted text-sm">Sirf admin ke liye</p>
        </div>
        <label className="block">
          <span className="text-sm font-medium">Username</span>
          <input className="input mt-1" required autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        <label className="block">
          <span className="text-sm font-medium">Password</span>
          <input className="input mt-1" type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        {error && <p className="text-sm text-danger">{error}</p>}
        <button className="btn btn-brand w-full py-3" disabled={busy}>{busy ? "…" : "Login"}</button>
      </form>
    </main>
  );
}
