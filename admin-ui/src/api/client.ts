import { clearCredentials, getAuthorizationHeader } from "@/lib/auth";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export async function apiGet<T>(
  path: string,
  params?: Record<string, string | number | undefined | null>,
): Promise<T> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") {
        url.searchParams.set(k, String(v));
      }
    }
  }
  const authorization = getAuthorizationHeader();
  const res = await fetch(url.toString(), {
    headers: {
      Accept: "application/json",
      ...(authorization ? { Authorization: authorization } : {}),
    },
  });
  if (res.status === 401) {
    clearCredentials();
  }
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}: ${await res.text()}`);
  }
  return res.json();
}
