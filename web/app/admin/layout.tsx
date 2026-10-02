"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getToken, setToken } from "@/lib/api";

const NAV = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/requests", label: "Requests" },
  { href: "/admin/shops", label: "Shops" },
  { href: "/admin/problems", label: "Masle" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const path = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
    else setReady(true);
  }, [router]);

  if (!ready) return null;

  return (
    <div className="flex-1 flex flex-col">
      <header className="border-b border-line bg-card">
        <div className="max-w-6xl mx-auto px-4 flex items-center gap-1 h-14 overflow-x-auto">
          <span className="font-bold mr-4 whitespace-nowrap">📒 EzKhata Admin</span>
          {NAV.map((n) => {
            const active = n.href === "/admin" ? path === "/admin" : path.startsWith(n.href);
            return (
              <Link key={n.href} href={n.href}
                className={`px-3 py-1.5 rounded-lg text-sm whitespace-nowrap ${active ? "bg-brand-soft text-brand font-semibold" : "text-muted"}`}>
                {n.label}
              </Link>
            );
          })}
          <button className="ml-auto text-sm text-muted whitespace-nowrap"
            onClick={() => { setToken(null); router.replace("/login"); }}>Logout</button>
        </div>
      </header>
      <main className="max-w-6xl w-full mx-auto px-4 py-6 flex-1">{children}</main>
    </div>
  );
}
