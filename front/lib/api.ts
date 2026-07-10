// Client API : toutes les requêtes passent par /api/* (proxifié vers Flask par
// next.config.mjs). Fetch côté client uniquement — la session Flask (cookie)
// suffit, pas de token à gérer.

export interface SessionUser {
  id: number;
  username: string;
}

export interface Article {
  id: number;
  source: string;
  url: string;
  title: string;
  title_original?: string;
  category: string | null;
  domain_slug: string;
  summary: string | null;
  excerpt: string;
  published_at: string | null;
  ingested_at: string | null;
  relevance: number | null;
  read?: boolean;
  saved?: boolean;
  takeaways?: string[];
  crossed?: number;
}

export interface ArticlesResponse {
  articles: Article[];
  total: number;
  personalized: boolean;
  logged_in: boolean;
  read_filter: string;
  domain: string | null;
  query: string;
  sort: string;
}

export interface ModelChoice {
  id: string;
  label: string;
  hint: string;
}

export interface SettingsResponse {
  keywords: string;
  hide_read: boolean;
  logged_in: boolean;
  model: string;
  models: ModelChoice[];
  ia_enabled: boolean;
  has_api_key: boolean;
  api_key_hint: string | null;
}

export interface ArticleDetail {
  article: Article;
  duplicates: { source: string; url: string; title: string }[];
  crossed: number;
  logged_in: boolean;
  is_read: boolean;
  saved: { folder_id: number | null } | null;
  saved_folder_name: string | null;
  folders: { id: number; name: string }[];
}

export interface Folder {
  id: number;
  name: string;
  count: number;
  articles: Article[];
}

export interface LibraryResponse {
  folders: Folder[];
  unfiled: Article[];
  total: number;
}

export interface TrendItem {
  term: string;
  recent: number;
  baseline: number;
  lift: number;
  sources: number;
  score: number;
  example: { id: number; title: string } | null;
  article_ids?: number[];
  articles?: Article[];
}

export interface TrendsResponse {
  trends: TrendItem[];
  weak: TrendItem[];
  recent_days: number;
}

export interface WeeklyDigest {
  week_start: string;
  week_end: string;
  content: string;
  article_count: number;
  model: string | null;
  generated_at: string | null;
}

export interface DigestResponse {
  digests: WeeklyDigest[];
  current_week: string;
  current_week_end: string;
  generating: boolean;
}

export interface Source {
  id: number;
  name: string;
  type: string;
  url: string;
  domain: string | null;
  domain_slug: string;
  authority: number | null;
  origin: string;
  quality: number | null;
  active: boolean;
  runs: number | null;
  added_at: string | null;
  last_checked: string | null;
}

export interface SourcesResponse {
  sources: Source[];
  discovery_enabled: boolean;
  refresh_running: boolean;
}

export interface Meta {
  app: string;
  domains: string[];
  discovery_enabled: boolean;
  semantic: boolean;
  ingest_running: boolean;
}

export interface AiStatus {
  ollama_available: boolean;
  ollama_model: string;
  has_env_key: boolean;
  models: ModelChoice[];
}

export interface JobStatus {
  running: boolean;
  done: boolean;
  percent: number;
  phase: string;
  ingested?: number;
  summarized?: number;
  found?: number;
  validated?: number;
  kept?: number;
  added?: number;
  removed?: number;
  active?: number;
  week?: string;
  error?: string | null;
}

export interface AccountResponse {
  user: { id: number; username: string; created_at: string };
  stats: { read: number; saved: number; folders: number };
  has_api_key: boolean;
  api_key_hint: string | null;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    credentials: "include",
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  const ct = res.headers.get("content-type") || "";
  const body: unknown = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const msg =
      body && typeof body === "object" && "error" in body
        ? String((body as Record<string, unknown>).error)
        : res.statusText;
    throw new ApiError(msg || "Erreur réseau", res.status);
  }
  return body as T;
}

const qs = (params: Record<string, string | undefined>) => {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) sp.set(k, v);
  const s = sp.toString();
  return s ? `?${s}` : "";
};

export const api = {
  meta: () => request<Meta>("/meta"),
  aiStatus: () => request<AiStatus>("/ai-status"),
  session: () => request<{ user: SessionUser | null }>("/session"),

  login: (username: string, password: string) =>
    request<{ user: SessionUser }>("/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),
  register: (
    username: string,
    password: string,
    confirm: string,
    key?: string,
    model?: string,
  ) =>
    request<{ user: SessionUser }>("/register", {
      method: "POST",
      body: JSON.stringify({ username, password, confirm, key, model }),
    }),
  logout: () => request<{ ok: boolean }>("/logout", { method: "POST" }),

  articles: (params: Record<string, string | undefined>) =>
    request<ArticlesResponse>(`/articles${qs(params)}`),
  article: (id: number) => request<ArticleDetail>(`/articles/${id}`),
  toggleRead: (id: number, read: boolean) =>
    request<{ read: boolean }>(`/articles/${id}/read`, {
      method: "POST",
      body: JSON.stringify({ read }),
    }),
  save: (id: number, opts: { folder_id?: number | null; new_folder?: string }) =>
    request<{ saved: boolean; folder_id: number | null }>(`/articles/${id}/save`, {
      method: "POST",
      body: JSON.stringify(opts),
    }),
  unsave: (id: number) =>
    request<{ saved: boolean }>(`/articles/${id}/unsave`, { method: "POST" }),

  ingestRefresh: () => request<{ started: boolean }>("/articles/refresh", { method: "POST" }),
  ingestStatus: () => request<JobStatus>("/articles/refresh/status"),

  library: () => request<LibraryResponse>("/library"),
  createFolder: (name: string) =>
    request<{ id: number; name: string }>("/folders", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  deleteFolder: (id: number) =>
    request<{ deleted: boolean }>(`/folders/${id}`, { method: "DELETE" }),

  trends: () => request<TrendsResponse>("/trends"),
  digest: () => request<DigestResponse>("/digest"),
  generateDigest: (week_start?: string) =>
    request<{ started: boolean }>("/digest/generate", {
      method: "POST",
      body: JSON.stringify(week_start ? { week_start } : {}),
    }),
  digestStatus: () => request<JobStatus>("/digest/generate/status"),

  sources: () => request<SourcesResponse>("/sources"),
  sourcesRefresh: () => request<{ started: boolean }>("/sources/refresh", { method: "POST" }),
  sourcesStatus: () => request<JobStatus>("/sources/refresh/status"),

  getSettings: () => request<SettingsResponse>("/settings"),
  saveSettings: (keywords: string, hide_read: boolean, model?: string) =>
    request<{ ok: boolean }>("/settings", {
      method: "POST",
      body: JSON.stringify({ keywords, hide_read, model }),
    }),

  account: () => request<AccountResponse>("/account"),
  setApiKey: (key: string) =>
    request<{ ok: boolean; has_api_key: boolean; api_key_hint: string | null }>(
      "/account/apikey",
      { method: "POST", body: JSON.stringify({ key }) },
    ),
  removeApiKey: () =>
    request<{ ok: boolean; has_api_key: boolean; api_key_hint: string | null }>(
      "/account/apikey",
      { method: "DELETE" },
    ),
  changePassword: (current: string, newPassword: string, confirm: string) =>
    request<{ ok: boolean }>("/account/password", {
      method: "POST",
      body: JSON.stringify({ current, new: newPassword, confirm }),
    }),
  deleteAccount: () => request<{ deleted: boolean }>("/account/delete", { method: "POST" }),
};
