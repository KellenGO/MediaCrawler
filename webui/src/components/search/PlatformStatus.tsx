import { Loader2, Check, Minus, AlertTriangle, XCircle, RotateCcw } from "lucide-react";
import type { PlatformSlug, PlatformStatus as PStatus, SearchJobResponse } from "@/types/search";
import { PLATFORM_LABELS, PLATFORM_COLORS } from "@/types/search";
import { statusLine } from "@/lib/statusDisplay";

interface PlatformStatusProps {
  response: SearchJobResponse | undefined;
  onRetry?: (platform: PlatformSlug) => void;
  retryingPlatform?: PlatformSlug | null;
  retryDisabled?: boolean;
}

const PLATFORM_ORDER: PlatformSlug[] = ["xhs", "douyin", "bilibili", "zhihu"];

/** 平台字母标记（效果稿：红 / 抖 / 哔 / 知）。 */
const PLATFORM_LETTERS: Record<PlatformSlug, string> = {
  xhs: "红",
  douyin: "抖",
  bilibili: "哔",
  zhihu: "知",
};

const RETRYABLE_STATUSES: PStatus[] = ["failed", "timed_out", "rate_limited", "login_required"];

function StatusTick({ status }: { status: PStatus }) {
  switch (status) {
    case "running":
      return <span className="w-[15px] h-[15px] rounded-full border-2 border-cyber-border-default border-t-brand animate-dsh-spin flex-shrink-0" />;
    case "succeeded":
      return <Check className="w-[16px] h-[16px] text-[#4f9e79] flex-shrink-0" />;
    case "empty":
      return <Minus className="w-[16px] h-[16px] text-cyber-text-muted flex-shrink-0" />;
    case "login_required":
    case "rate_limited":
      return <AlertTriangle className="w-[16px] h-[16px] text-warn flex-shrink-0" />;
    case "timed_out":
    case "failed":
      return <XCircle className="w-[16px] h-[16px] text-danger flex-shrink-0" />;
    case "cancelled":
      return <Minus className="w-[16px] h-[16px] text-cyber-text-muted flex-shrink-0" />;
    default:
      return <Minus className="w-[16px] h-[16px] text-cyber-text-muted/50 flex-shrink-0" />;
  }
}

export function PlatformStatus({
  response,
  onRetry,
  retryingPlatform,
  retryDisabled,
}: PlatformStatusProps) {
  // 无任务：显示四张浅色骨架卡
  if (!response) {
    return (
      <div className="flex gap-2.5 overflow-x-auto md:grid md:grid-cols-2 lg:grid-cols-4 md:overflow-visible mt-5">
        {PLATFORM_ORDER.map((p) => (
          <div
            key={p}
            className="min-w-[170px] md:min-w-0 flex-1 flex items-center gap-3 rounded-[15px] border border-cyber-border-subtle bg-cyber-bg-secondary px-3.5 py-3 opacity-50"
          >
            <span
              className="w-[34px] h-[34px] rounded-[10px] grid place-items-center font-extrabold text-[14px] flex-shrink-0"
              style={{ backgroundColor: PLATFORM_COLORS[p] + "1f", color: PLATFORM_COLORS[p] }}
            >
              {PLATFORM_LETTERS[p]}
            </span>
            <div className="min-w-0">
              <strong className="text-[13px] text-cyber-text-primary block">{PLATFORM_LABELS[p]}</strong>
              <small className="text-[11px] text-cyber-text-muted block truncate">等待中</small>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="mt-5">
      <div className="flex gap-2.5 overflow-x-auto md:grid md:grid-cols-2 lg:grid-cols-4 md:overflow-visible">
        {PLATFORM_ORDER.map((p) => {
          const info = response.platforms[p];
          if (!info) return null;

          const status: PStatus = info.status;
          const isRetrying = retryingPlatform === p;
          const retryable = onRetry ? RETRYABLE_STATUSES.includes(status) : false;

          return (
            <div
              key={p}
              className={`min-w-[170px] md:min-w-0 flex-1 flex items-center gap-3 rounded-[15px] border bg-cyber-bg-secondary px-3.5 py-3 transition-colors ${
                status === "running"
                  ? "border-brand/40"
                  : status === "succeeded" || status === "empty"
                    ? "border-cyber-border-subtle"
                    : status === "login_required" || status === "rate_limited"
                      ? "border-warn/40"
                      : status === "failed" || status === "timed_out"
                        ? "border-danger/40"
                        : "border-cyber-border-subtle"
              }`}
            >
              <span
                className="w-[34px] h-[34px] rounded-[10px] grid place-items-center font-extrabold text-[14px] flex-shrink-0"
                style={{ backgroundColor: PLATFORM_COLORS[p] + "1f", color: PLATFORM_COLORS[p] }}
              >
                {PLATFORM_LETTERS[p]}
              </span>
              <div className="min-w-0 flex-1">
                <strong className="text-[13px] text-cyber-text-primary block">{PLATFORM_LABELS[p]}</strong>
                <small className="text-[11px] text-cyber-text-muted block truncate">
                  {statusLine(status, info)}
                </small>
              </div>
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {isRetrying ? (
                  <span className="flex items-center gap-1 text-[11px] text-brand-strong">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    重试
                  </span>
                ) : (
                  <StatusTick status={status} />
                )}
                {retryable && !isRetrying && (
                  <button
                    type="button"
                    disabled={retryDisabled}
                    onClick={(e) => {
                      e.stopPropagation();
                      onRetry?.(p);
                    }}
                    title={`重试 ${PLATFORM_LABELS[p]}`}
                    className="flex items-center gap-1 rounded-md border border-brand/40 px-1.5 py-0.5 text-[10.5px] text-brand-strong hover:bg-brand-soft transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <RotateCcw className="w-3 h-3" />重试
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 整体状态（克制浅色） */}
      {response.overall !== "running" && (
        <div
          className={`mt-2.5 inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-[12px] ${
            response.overall === "completed"
              ? "border-ok/30 bg-ok-soft text-[#3d7d60]"
              : response.overall === "partial" || response.overall === "cancelling"
                ? "border-warn/30 bg-warn-soft text-warn"
                : response.overall === "cancelled"
                  ? "border-cyber-border-subtle bg-cyber-bg-tertiary text-cyber-text-muted"
                  : "border-danger/30 bg-danger-soft text-danger"
          }`}
        >
          {response.overall === "completed"
            ? "✓ 全部完成"
            : response.overall === "partial"
              ? "⚠ 部分成功"
              : response.overall === "cancelling"
                ? "正在取消"
                : response.overall === "cancelled"
                  ? "搜索已取消"
                  : "✗ 搜索失败"}
        </div>
      )}
    </div>
  );
}
