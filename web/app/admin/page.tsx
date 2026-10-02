"use client";

import Link from "next/link";
import { Loading, PageTitle } from "@/components/ui";
import { useApi } from "@/lib/useApi";

type Overview = {
  shops: number; shops_on: number; users: number; employees: number; pending_requests: number;
  messages_today: number; not_understood_today: number; not_understood_pct: number; errors_today: number;
  undelivered_today: number; active_shops_today: number; whatsapp: string;
};

function Stat({ label, value, sub, tone, href }: { label: string; value: React.ReactNode; sub?: string; tone?: "warn" | "danger" | "brand"; href?: string }) {
  const color = tone === "danger" ? "text-danger" : tone === "warn" ? "text-warn" : tone === "brand" ? "text-brand" : "";
  const body = (
    <div className="card p-4 h-full">
      <div className="text-sm text-muted">{label}</div>
      <div className={`text-3xl font-bold mt-1 tabular-nums ${color}`}>{value}</div>
      {sub && <div className="text-xs text-muted mt-1">{sub}</div>}
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

export default function OverviewPage() {
  const { data, error, loading, reload } = useApi<Overview>("/api/admin/overview");

  return (
    <>
      <PageTitle title="Overview" sub="Aaj ka haal (Pakistan time)" right={<button className="btn" onClick={reload}>↻ Refresh</button>} />
      <Loading error={error} loading={loading && !data} />
      {data && (
        <div className="space-y-6">
          <div className={`card p-4 flex items-center gap-3 ${data.whatsapp === "open" ? "" : "bg-danger-soft"}`}>
            <span className="text-2xl">{data.whatsapp === "open" ? "🟢" : "🔴"}</span>
            <div>
              <div className="font-semibold">WhatsApp {data.whatsapp === "open" ? "jura hua hai" : "jura nahi hai"}</div>
              <div className="text-sm text-muted">Haal: {data.whatsapp}</div>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Pending requests" value={data.pending_requests} tone={data.pending_requests ? "warn" : undefined} href="/admin/requests" />
            <Stat label="Dukaanen" value={data.shops} sub={`${data.shops_on} chalu · ${data.shops - data.shops_on} band`} href="/admin/shops" />
            <Stat label="Users" value={data.users} />
            <Stat label="Employees" value={data.employees} />
          </div>

          <div>
            <h2 className="font-semibold mb-3">Aaj</h2>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              <Stat label="Messages" value={data.messages_today} sub={`${data.active_shops_today} dukaanon se`} />
              <Stat label="Nahi samjhe" value={data.not_understood_today} sub={`${data.not_understood_pct}% messages`}
                tone={data.not_understood_pct > 10 ? "danger" : data.not_understood_today ? "warn" : "brand"} href="/admin/problems" />
              <Stat label="Errors" value={data.errors_today} tone={data.errors_today ? "danger" : "brand"} href="/admin/problems" />
              <Stat label="Jawab nahi pohncha" value={data.undelivered_today} tone={data.undelivered_today ? "danger" : "brand"} href="/admin/problems" />
              <Stat label="Active dukaanen" value={data.active_shops_today} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
