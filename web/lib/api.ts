// Talks to the EzKhata backend on Render. The admin token lives in sessionStorage (cleared when the tab closes).

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

const TOKEN_KEY = "ezkhata_admin_token";

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode: login lasts only for this page */
  }
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string) {
    super(message);
  }
}

export async function api<T = unknown>(path: string, options: { method?: string; body?: unknown; auth?: boolean } = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.auth !== false) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: options.method || "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  } catch {
    throw new ApiError(0, "Server se rabta nahi ho saka. Thori der baad try karein (server jaag raha ho sakta hai).");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data?.detail;
    const message = typeof detail === "object" && detail?.message ? detail.message
      : Array.isArray(detail) ? "Form ki maloomat theek nahi." : "Kuch ghalat ho gaya.";
    if (res.status === 401 && options.auth !== false) {
      setToken(null);
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) window.location.href = "/login";
    }
    throw new ApiError(res.status, message, detail?.code);
  }
  return data as T;
}

export function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-PK", {
    timeZone: "Asia/Karachi", day: "numeric", month: "short", hour: "numeric", minute: "2-digit",
  });
}

export function phone(p: string): string {
  return p.startsWith("92") && p.length === 12 ? `0${p.slice(2, 5)}-${p.slice(5)}` : p;
}
