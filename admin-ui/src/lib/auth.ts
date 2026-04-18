const AUTH_STORAGE_KEY = "admin.basic_auth";
export const AUTH_CHANGED_EVENT = "admin:auth-changed";

export interface BasicAuthCredentials {
  username: string;
  password: string;
}

function notifyAuthChanged() {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(AUTH_CHANGED_EVENT));
}

export function saveCredentials(credentials: BasicAuthCredentials): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(credentials));
  notifyAuthChanged();
}

export function clearCredentials(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(AUTH_STORAGE_KEY);
  notifyAuthChanged();
}

export function getStoredCredentials(): BasicAuthCredentials | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<BasicAuthCredentials>;
    if (typeof parsed.username !== "string" || typeof parsed.password !== "string") {
      return null;
    }
    return { username: parsed.username, password: parsed.password };
  } catch {
    return null;
  }
}

export function hasStoredCredentials(): boolean {
  return getStoredCredentials() !== null;
}

export function getAuthorizationHeader(): string | undefined {
  const credentials = getStoredCredentials();
  if (!credentials) return undefined;
  const encoded = window.btoa(`${credentials.username}:${credentials.password}`);
  return `Basic ${encoded}`;
}
