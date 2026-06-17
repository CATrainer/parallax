// TypeScript interfaces mirroring backend/app/schemas/domain.py.
// Every API response is wrapped in the standard envelope (§8.1).

export interface Envelope<T> {
  ok: boolean;
  data: T | null;
  meta?: { computed_at?: string; from_cache?: boolean };
  error?: { code: string; message: string };
}

// ── Signals ──
export interface SignalOut {
  id: string;
  signal_type: string;
  fired: boolean;
  strength: number;
  raw_evidence: string;
  source: string;
  source_ref?: string | null;
  observed_at: string;
  decays: string;
}

// ── Ownership ──
export interface OwnerOut {
  id: string;
  owner_type: string;
  display_name: string;
  company_number?: string | null;
}

export interface OwnershipLinkOut {
  id: string;
  role: string;
  is_current: boolean;
  source: string;
  link_confidence: number;
  owner: OwnerOut;
}

// ── Site ──
export interface SiteOut {
  uprn: string;
  address: string;
  postcode?: string | null;
  lat?: number | null;
  lng?: number | null;
  property_type?: string | null;
  tenure?: string | null;
  local_authority?: string | null;
  resolution_confidence: number;
}

export interface SiteDetail extends SiteOut {
  ownership: OwnershipLinkOut[];
  signals: SignalOut[];
  headline_conviction?: number | null;
  headline_band?: string | null;
}

// ── Briefing ──
export interface BriefingParagraph {
  text: string;
  cited_signal_ids: string[];
}

export interface Conclusion {
  type: string;
  statement: string;
  confidence: number;
  contributing_signal_ids: string[];
}

export interface BriefingOut {
  id: string;
  site_uprn: string;
  lede: string;
  paragraphs: BriefingParagraph[];
  takeaway: string;
  conclusions: Conclusion[];
  conviction: number;
  band: string;
  opportunity_types: string[];
  headline_opportunity?: string | null;
  signals: SignalOut[];
  ownership: OwnershipLinkOut[];
  site: SiteOut;
  synthesis_model?: string | null;
  is_stale: boolean;
  computed_at?: string | null;
}

export interface BriefingCard {
  id: string;
  site_uprn: string;
  address: string;
  postcode?: string | null;
  lede: string;
  conviction: number;
  band: string;
  headline_opportunity?: string | null;
  opportunity_types: string[];
  signal_count: number;
  updated_at?: string | null;
}

// ── Validation ──
export interface ProvenanceEntry {
  check: string;
  source: string;
  cost_credits: number;
  result: string;
}

export interface ValidationOut {
  id: string;
  site_uprn: string;
  status: string;
  credits_spent: number;
  confirmed_ownership?: Record<string, unknown> | null;
  occupancy_status?: string | null;
  contact_route?: Record<string, unknown> | null;
  updated_conviction?: number | null;
  provenance_log: ProvenanceEntry[];
  error?: string | null;
}

export interface ValidationJob {
  id: string;
  status: string;
  credits_remaining: number;
}

// ── Patch ──
export interface BuyBox {
  min_price?: number | null;
  max_price?: number | null;
  property_types: string[];
}

export interface PatchIn {
  name: string;
  postcodes: string[];
  buy_box: BuyBox;
  opportunity_types: string[];
  conviction_floor: number;
}

export interface PatchOut extends PatchIn {
  id: string;
}

// ── Watchlist / status ──
export type WatchStatus = "pursuing" | "watching" | "dead";

export interface WatchlistIn {
  site_uprn: string;
  status?: WatchStatus;
  note?: string | null;
}

export interface WatchlistOut {
  id: string;
  site_uprn: string;
  status: string;
  note?: string | null;
  address?: string | null;
  conviction?: number | null;
  band?: string | null;
}

export interface StatusIn {
  status: "pursuing" | "dead";
}

// ── Usage / auth ──
export interface UsageOut {
  rung: string;
  credits_remaining: number;
  deep_dives_used: number;
}

export interface SearchResult {
  kind: "site" | "company" | "person";
  uprn?: string | null;
  label: string;
  sublabel?: string | null;
  conviction?: number | null;
  band?: string | null;
}

export interface LoginIn {
  email: string;
  password: string;
}

export interface TokenOut {
  access_token: string;
  token_type: string;
  rung: string;
  is_broker: boolean;
}

// ── Broker (Product 2, §11) ──
export interface BrokerEnrichRow {
  input_address: string;
  uprn?: string | null;
  resolved_address?: string | null;
  transaction_likelihood: number;
  band: string;
  rationale: string;
  signal_summary: string[];
}

export interface BrokerEnrichOut {
  rows: BrokerEnrichRow[];
  total: number;
}

export interface BrokerIntelligenceOut {
  site: SiteOut;
  owner_situation: string;
  mortgage_event_likelihood: number;
  band: string;
  drivers: string[];
  ownership: OwnershipLinkOut[];
}
