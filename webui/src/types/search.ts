export type PlatformSlug = "xhs" | "douyin" | "bilibili" | "zhihu";

export type PlatformStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "empty"
  | "login_required"
  | "rate_limited"
  | "timed_out"
  | "failed"
  | "cancelled";

export type OverallStatus = "running" | "completed" | "partial" | "failed" | "cancelling" | "cancelled";

export interface UnifiedSearchResult {
  platform: PlatformSlug;
  content_id: string;
  content_type: string;
  title: string;
  author: string | null;
  url: string;
  published_at: string | null;
  cover_url: string | null;
  metrics: Record<string, number>;
  rank: number;
}

export interface PlatformStatusInfo {
  status: PlatformStatus;
  result_count: number;
  error_summary: string | null;
}

export interface SearchJobResponse {
  job_id: string;
  overall: OverallStatus;
  keyword: string;
  created_at: string;
  completed_at: string | null;
  platforms: Record<PlatformSlug, PlatformStatusInfo>;
  results: UnifiedSearchResult[];
}

export interface SearchJobRequest {
  keyword: string;
  platforms?: PlatformSlug[];
  limit_per_platform?: number;
}

export const PLATFORM_LABELS: Record<PlatformSlug, string> = {
  xhs: "小红书",
  douyin: "抖音",
  bilibili: "B站",
  zhihu: "知乎",
};

export const PLATFORM_COLORS: Record<PlatformSlug, string> = {
  xhs: "#FF2442",
  douyin: "#000000",
  bilibili: "#00A1D6",
  zhihu: "#0066FF",
};

export const PLATFORM_ICONS: Record<PlatformSlug, string> = {
  xhs: "📕",
  douyin: "🎵",
  bilibili: "📺",
  zhihu: "💡",
};

export const STATUS_LABELS: Record<PlatformStatus, string> = {
  pending: "等待中",
  running: "搜索中",
  succeeded: "已完成",
  empty: "无结果",
  login_required: "需要登录",
  rate_limited: "请求受限，稍后重试",
  timed_out: "超时",
  failed: "失败",
  cancelled: "已取消",
};
