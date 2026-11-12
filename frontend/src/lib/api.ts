import type {
  AnalysisResponse,
  AppConfig,
  HealthResponse,
  JournalEntry,
  CredentialsView,
  KpiSettings,
  MetrikaData,
  ServerLogData,
  Source,
} from "./types";

const API_KEY_STORAGE = "adassistant_api_key";

export function getApiKey(): string {
  return localStorage.getItem(API_KEY_STORAGE) ?? "";
}

export function setApiKey(key: string): void {
  if (key.trim()) localStorage.setItem(API_KEY_STORAGE, key.trim());
  else localStorage.removeItem(API_KEY_STORAGE);
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  const key = getApiKey();
  if (key) headers.set("X-API-Key", key);

  let response: Response;
  try {
    response = await fetch(path, { ...init, headers });
  } catch {
    throw new ApiError("Сервер недоступен. Проверьте, что бэкенд запущен, и повторите попытку.", 0);
  }

  if (!response.ok) {
    let detail = `Ошибка ${response.status}`;
    try {
      const data = await response.json();
      if (typeof data?.detail === "string") detail = data.detail;
      else if (Array.isArray(data?.detail)) detail = data.detail.map((d: { msg?: string }) => d.msg).join("; ");
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  config: () => request<AppConfig>("/api/config"),
  settings: () => request<KpiSettings>("/api/settings"),
  saveSettings: (kpi: KpiSettings) =>
    request<KpiSettings>("/api/settings", { method: "PUT", body: JSON.stringify(kpi) }),
  analyze: () =>
    request<AnalysisResponse>("/api/analyze", { method: "POST", body: JSON.stringify({}) }),
  journal: () => request<JournalEntry[]>("/api/journal"),
  confirm: (id: string, confirmedBy: string) =>
    request<{ message: string; status: string }>(`/api/recommendations/${id}/confirm`, {
      method: "POST",
      body: JSON.stringify({ confirmed_by: confirmedBy }),
    }),
  reject: (id: string, confirmedBy: string) =>
    request<{ message: string; status: string }>(`/api/recommendations/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ confirmed_by: confirmedBy }),
    }),
  credentials: () => request<CredentialsView>("/api/credentials"),
  saveCredentials: (source: Source, body: { values: Record<string, string>; clear: string[] }) =>
    request<CredentialsView>(`/api/credentials/${source}`, { method: "PUT", body: JSON.stringify(body) }),
  testCredentials: () =>
    request<{ sources: { source: string; ok: boolean; message: string }[] }>("/api/credentials/test", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  metrika: (days: number) => request<MetrikaData>(`/api/metrika?days=${days}`),
  serverlog: (days: number) => request<ServerLogData>(`/api/serverlog?days=${days}`),
  journalCsvUrl: "/api/journal.csv",
};
