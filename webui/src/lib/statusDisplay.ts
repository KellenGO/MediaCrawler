/**
 * 平台状态卡片显示纯逻辑（Phase 1 耗时指标展示，无 React 依赖）。
 *
 * 只做"把数字格式化成文案"，不含任何网络/状态机逻辑，测试直接 import 本模块。
 */

import type {
  PlatformStatus as PStatus,
  PlatformStatusInfo,
} from "../types/search.js";
import { STATUS_LABELS } from "../types/search.js";

export const TERMINAL_STATUSES: ReadonlySet<PStatus> = new Set([
  "succeeded", "empty", "login_required", "rate_limited", "timed_out", "failed", "cancelled",
]);

export function formatSeconds(ms: number | null | undefined): string | null {
  if (ms == null) return null;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** 终态耗时行：`首条 1.3s · 完成 4.8s`；无数据返回 null（不占位）。 */
export function timingLine(info: PlatformStatusInfo): string | null {
  const t = info.timings;
  if (!t) return null;
  const first = formatSeconds(t.first_result_ms);
  const total = formatSeconds(t.total_ms);
  if (first && total) return `首条 ${first} · 完成 ${total}`;
  if (total) return `完成 ${total}`;
  if (first) return `首条 ${first}`;
  return null;
}

/** 状态卡主文案：终态且有时耗时，追加耗时行。 */
export function statusLine(status: PStatus, info: PlatformStatusInfo): string {
  let base: string;
  switch (status) {
    case "running":
      base = "正在检索…";
      break;
    case "succeeded":
      base = `${info.result_count} 条结果`;
      break;
    case "empty":
      base = "无结果";
      break;
    case "login_required":
      base = "需要登录";
      break;
    case "rate_limited":
      base = "请求受限";
      break;
    case "timed_out":
      base = "超时";
      break;
    case "failed":
      base = info.error_summary || "失败";
      break;
    case "cancelled":
      base = "已取消";
      break;
    default:
      base = STATUS_LABELS[status];
  }
  if (TERMINAL_STATUSES.has(status)) {
    const timing = timingLine(info);
    if (timing) return `${base} · ${timing}`;
  }
  return base;
}
