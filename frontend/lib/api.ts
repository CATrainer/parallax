// Typed fetch client. Unwraps the standard envelope (§8.1), throws ApiError
// on { ok: false }, attaches the bearer token, and exposes one typed method
// per endpoint the frontend uses (§8.2 / §8.3).

import { getToken, clearToken } from "./auth";
import type {
  BriefingCard,
  BriefingOut,
  BrokerEnrichOut,
  BrokerIntelligenceOut,
  PatchIn,
  PatchOut,
  SearchResult,
  SiteDetail,
  TokenOut,
  UsageOut,
  ValidationJob,
  ValidationOut,
  WatchlistOut,
  WatchStatus,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ||
  "http://localhost:8003";

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | undefined>;
  /** Skip attaching the bearer token (login/register). */
  noAuth?: boolean;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, noAuth } = opts;

  let url = `${API_BASE}/api${path}`;
  if (query) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    }
    const s = qs.toString();
    if (s) url += `?${s}`;
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (!noAuth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      "NETWORK",
      "Could not reach the engine. Check your connection and try again.",
      0,
    );
  }

  // 401 → token is gone or invalid; clear it so the app redirects to login.
  if (res.status === 401) {
    clearToken();
    throw new ApiError("UNAUTHORIZED", "Your session expired. Sign in again.", 401);
  }

  let payload: unknown;
  try {
    payload = await res.json();
  } catch {
    throw new ApiError(
      "BAD_RESPONSE",
      "The engine returned an unreadable response. Try again shortly.",
      res.status,
    );
  }

  const env = payload as {
    ok?: boolean;
    data?: T;
    error?: { code?: string; message?: string };
  };

  if (env && env.ok === false) {
    throw new ApiError(
      env.error?.code || "ERROR",
      env.error?.message || "Something went wrong handling that request.",
      res.status,
    );
  }

  if (!res.ok) {
    throw new ApiError("HTTP_ERROR", `Request failed (${res.status}).`, res.status);
  }

  return (env?.data ?? (payload as T)) as T;
}

export const api = {
  // ── Auth ──
  login(email: string, password: string): Promise<TokenOut> {
    return request<TokenOut>("/auth/login", {
      method: "POST",
      body: { email, password },
      noAuth: true,
    });
  },

  // ── Usage ──
  usage(): Promise<UsageOut> {
    return request<UsageOut>("/usage");
  },

  // ── Search (pull entry) ──
  search(q: string, type?: string): Promise<SearchResult[]> {
    return request<SearchResult[]>("/search", { query: { q, type } });
  },

  // ── Sites / briefings ──
  site(uprn: string): Promise<SiteDetail> {
    return request<SiteDetail>(`/sites/${encodeURIComponent(uprn)}`);
  },
  briefing(uprn: string): Promise<BriefingOut> {
    return request<BriefingOut>(`/sites/${encodeURIComponent(uprn)}/briefing`);
  },

  // ── Validation (metered) ──
  startValidation(uprn: string): Promise<ValidationJob> {
    return request<ValidationJob>(
      `/sites/${encodeURIComponent(uprn)}/validate`,
      { method: "POST" },
    );
  },
  validation(id: string): Promise<ValidationOut> {
    return request<ValidationOut>(`/validations/${encodeURIComponent(id)}`);
  },

  // ── Patch (push) ──
  getPatch(): Promise<PatchOut> {
    return request<PatchOut>("/patch");
  },
  savePatch(patch: PatchIn): Promise<PatchOut> {
    return request<PatchOut>("/patch", { method: "POST", body: patch });
  },
  patchBriefings(params?: {
    since?: string;
    band?: string;
    type?: string;
  }): Promise<BriefingCard[]> {
    return request<BriefingCard[]>("/patch/briefings", { query: params });
  },

  // ── Watchlist / status ──
  watchlist(): Promise<WatchlistOut[]> {
    return request<WatchlistOut[]>("/watchlist");
  },
  addToWatchlist(site_uprn: string, status: WatchStatus = "watching"): Promise<WatchlistOut> {
    return request<WatchlistOut>("/watchlist", {
      method: "POST",
      body: { site_uprn, status },
    });
  },
  setStatus(uprn: string, status: "pursuing" | "dead"): Promise<WatchlistOut> {
    return request<WatchlistOut>(`/sites/${encodeURIComponent(uprn)}/status`, {
      method: "POST",
      body: { status },
    });
  },

  // ── Broker (Product 2) ──
  brokerEnrich(addresses: string[]): Promise<BrokerEnrichOut> {
    return request<BrokerEnrichOut>("/broker/enrich", {
      method: "POST",
      body: { list: addresses },
    });
  },
  brokerIntelligence(uprn: string): Promise<BrokerIntelligenceOut> {
    return request<BrokerIntelligenceOut>(
      `/broker/site/${encodeURIComponent(uprn)}/intelligence`,
    );
  },
};

export { API_BASE };
