export type Source = "yandex" | "google";
export type ActionType = "bid" | "minus_words" | "budget";
export type Priority = "high" | "medium" | "low";
export type Status = "proposed" | "confirmed" | "failed" | "rejected" | "stale";

export interface PeriodStats {
  label: string;
  date_from: string;
  date_to: string;
  impressions: number;
  clicks: number;
  cost: number;
  conversions: number;
  ctr: number;
  cpc: number;
  cpa: number | null;
  days: number;
  cost_per_day: number;
}

export interface CampaignStat {
  id: string;
  name: string;
  source: Source;
  impressions: number;
  clicks: number;
  cost: number;
  conversions: number;
  ctr: number;
  cpc: number;
  cpa: number | null;
  daily_budget: number | null;
  status: string;
}

export interface CampaignStatPeriods {
  campaign: CampaignStat;
  last7: PeriodStats;
  lastDay: PeriodStats;
}

export interface MutationChange {
  entity: string;
  entity_id: string;
  entity_name: string;
  field: "bid" | "minus_words" | "daily_budget";
  before: string;
  after: string;
  payload: Record<string, unknown>;
}

export interface Recommendation {
  id: string;
  source: Source;
  campaign_id: string;
  campaign_name: string;
  action_type: ActionType;
  title: string;
  reason: string;
  priority: Priority;
  metric_snapshot: Record<string, number | null>;
  changes: MutationChange[];
  created_at: string;
  status: Status;
}

export interface KpiSettings {
  target_cpa: number;
  target_ctr: number;
  daily_budget: number;
  currency: string;
  overrun_tolerance_pct: number;
  ctr_deficit_tolerance_pct: number;
  cpa_overrun_tolerance_pct: number;
  min_clicks_for_judgement: number;
  bid_step_pct: number;
  allowed_sources: Source[];
}

export interface AnalysisResponse {
  generated_at: string;
  kpi: KpiSettings;
  summary: PeriodStats;
  by_source: Record<string, PeriodStats>;
  campaigns: CampaignStatPeriods[];
  recommendations: Recommendation[];
  anomalies: string[];
  warnings: string[];
}

export interface JournalEntry {
  id: string;
  created_at: string;
  campaign_name: string;
  source: Source;
  action_type: ActionType;
  status: Status;
  confirmed_by: string | null;
  confirmed_at: string | null;
  title: string;
  result: string;
  details: string;
}

export interface HealthSource {
  source: string;
  ok: boolean;
  message: string;
}

export interface HealthResponse {
  app: string;
  mock_mode: boolean;
  sources: HealthSource[];
}

export interface AppConfig {
  app: string;
  currency: string;
  mock_mode: boolean;
  sources: Record<string, { configured: boolean; label: string; missing: string[] }>;
}

export interface CredentialField {
  key: string;
  env: string;
  label: string;
  hint: string;
  secret: boolean;
  filled: boolean;
  preview: string;
}

export interface CredentialSource {
  source: Source;
  label: string;
  ready: boolean;
  fields: CredentialField[];
}

export interface CredentialsView {
  sources: CredentialSource[];
  mock_mode: boolean;
  storage_note: string;
}

export interface MetrikaGoal {
  goal_id: string;
  name: string;
  reaches: number;
  is_download: boolean;
}

export interface MetrikaData {
  ok: boolean;
  message: string;
  counter?: string;
  date_from?: string;
  date_to?: string;
  visits?: number;
  users?: number;
  pageviews?: number;
  bounce_rate?: number;
  avg_duration?: number;
  downloads?: number;
  by_day?: { date: string; visits: number; users: number }[];
  goals?: MetrikaGoal[];
  sources?: { source: string; visits: number }[];
}

export interface ServerLogEvent {
  at: string;
  date: string;
  ip: string;
  file: string;
  size_kb: number;
  status: number;
}

export interface ServerLogData {
  ok: boolean;
  message: string;
  path?: string;
  events?: ServerLogEvent[];
  summary?: { total: number; today: number; yesterday: number; unique_ips: number; errors: number; days: number };
  by_day?: { date: string; count: number }[];
  by_hour?: { hour: string; count: number }[];
  top_files?: { file: string; count: number }[];
}
