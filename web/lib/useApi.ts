"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api";

/** Load data from the backend; `reload()` fetches it again after a change. */
export function useApi<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api<T>(path));
      setError("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Kuch ghalat ho gaya.");
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    reload();
  }, [reload]);

  return { data, error, loading, reload };
}
