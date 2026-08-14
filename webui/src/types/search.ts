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

export interface PlatformTimingInfo {
  /** worker 子进程创建耗时（毫秒） */
  spawn_ms: number | null;
  /** 从 job 开始到该平台首条合法结果（毫秒） */
  first_result_ms: number | null;
  /** 平台进入终态的总耗时（毫秒） */
  total_ms: number | null;
}

export interface PlatformStatusInfo {
  status: PlatformStatus;
  result_count: number;
  error_summary: string | null;
  /** 耗时指标；后端无数据时为 null，旧响应可能缺失 */
  timings?: PlatformTimingInfo | null;
}

export interface SearchJobResponse {
  job_id: string;
  overall: OverallStatus;
  keyword: string;
  created_at: string;
  completed_at: string | null;
  /** job 级总耗时（毫秒）；job 未完成时为 null */
  total_ms?: number | null;
  platforms: Record<PlatformSlug, PlatformStatusInfo>;
  results: UnifiedSearchResult[];
}

export interface SearchJobRequest {
  keyword: string;
  platforms?: PlatformSlug[];
  limit_per_platform?: number;
  /** Round 15: 按平台独立数量（1–20 整数）；缺失平台回退 limit_per_platform。 */
  platform_limits?: Partial<Record<PlatformSlug, number>>;
}

export const PLATFORM_LABELS: Record<PlatformSlug, string> = {
  xhs: "小红书",
  douyin: "抖音",
  bilibili: "B站",
  zhihu: "知乎",
};

export const PLATFORM_COLORS: Record<PlatformSlug, string> = {
  xhs: "#e9545d",
  douyin: "#2d3436",
  bilibili: "#3d99bf",
  zhihu: "#2768d9",
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
