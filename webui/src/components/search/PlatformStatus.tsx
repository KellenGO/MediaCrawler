import { Loader2, CheckCircle2, AlertTriangle, Clock, XCircle, Circle } from "lucide-react";
import type { PlatformSlug, PlatformStatus as PStatus, SearchJobResponse } from "@/types/search";
import {
  PLATFORM_LABELS,
  PLATFORM_ICONS,

  STATUS_LABELS,
} from "@/types/search";

interface PlatformStatusProps {
  response: SearchJobResponse | undefined;
}

const PLATFORM_ORDER: PlatformSlug[] = ["xhs", "douyin", "bilibili", "zhihu"];

function StatusIcon({ status }: { status: PStatus }) {
  switch (status) {
    case "running":
      return <Loader2 className="w-4 h-4 animate-spin text-cyber-neon-cyan" />;
    case "succeeded":
      return <CheckCircle2 className="w-4 h-4 text-cyber-neon-green" />;
    case "empty":
      return <Circle className="w-4 h-4 text-cyber-text-muted" />;
    case "login_required":
      return <AlertTriangle className="w-4 h-4 text-cyber-neon-orange" />;
    case "rate_limited":
      return <Clock className="w-4 h-4 text-cyber-neon-orange" />;
    case "timed_out":
      return <Clock className="w-4 h-4 text-cyber-neon-pink" />;
    case "failed":
      return <XCircle className="w-4 h-4 text-cyber-neon-pink" />;
    case "cancelled":
      return <Circle className="w-4 h-4 text-cyber-text-muted" />;
    default:
      return <Circle className="w-4 h-4 text-cyber-text-muted opacity-50" />;
  }
}

export function PlatformStatus({ response }: PlatformStatusProps) {
  // Show skeleton when no response yet
  if (!response) {
    return (
      <div className="flex justify-center gap-4 mt-4">
        {PLATFORM_ORDER.map((p) => (
          <div
            key={p}
            className="flex items-center gap-2 px-3 py-2 rounded-lg border border-cyber-border-subtle bg-cyber-bg-tertiary opacity-50"
          >
            <span className="text-sm">{PLATFORM_ICONS[p]}</span>
            <span className="text-xs font-mono text-cyber-text-muted">
              {PLATFORM_LABELS[p]}
            </span>
            <Circle className="w-3 h-3 text-cyber-text-muted" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-wrap justify-center gap-3 mt-4">
      {PLATFORM_ORDER.map((p) => {
        const info = response.platforms[p];
        if (!info) return null;

        const status: PStatus = info.status;

        const cancelled = status === "cancelled";

        return (
          <div
            key={p}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-mono transition-all ${
              status === "running"
                ? "border-cyber-neon-cyan/50 bg-cyber-neon-cyan/5 text-cyber-neon-cyan"
                : status === "succeeded"
                  ? "border-cyber-neon-green/50 bg-cyber-neon-green/5 text-cyber-neon-green"
                  : status === "empty"
                    ? "border-cyber-border-subtle bg-cyber-bg-tertiary text-cyber-text-muted"
                    : status === "login_required" || status === "rate_limited"
                      ? "border-cyber-neon-orange/50 bg-cyber-neon-orange/5 text-cyber-neon-orange"
                      : cancelled
                        ? "border-cyber-border-subtle bg-cyber-bg-tertiary text-cyber-text-muted"
                        : status === "failed" || status === "timed_out"
                          ? "border-cyber-neon-pink/50 bg-cyber-neon-pink/5 text-cyber-neon-pink"
                          : "border-cyber-border-subtle bg-cyber-bg-tertiary text-cyber-text-muted"
            }`}
          >
            <span className="text-sm">{PLATFORM_ICONS[p]}</span>
            <span>{PLATFORM_LABELS[p]}</span>
            <StatusIcon status={status} />
            <span>{STATUS_LABELS[status]}</span>
            {info.result_count > 0 && (
              <span className="ml-1 px-1.5 py-0.5 rounded bg-cyber-bg-secondary text-[10px]">
                {info.result_count}
              </span>
            )}
          </div>
        );
      })}

      {/* Overall status badge */}
      {response.overall !== "running" && (
        <div
          className={`flex items-center gap-1 px-3 py-2 rounded-lg border text-xs font-mono ${
            response.overall === "completed"
              ? "border-cyber-neon-green bg-cyber-neon-green/10 text-cyber-neon-green"
              : response.overall === "partial"
                ? "border-cyber-neon-orange bg-cyber-neon-orange/10 text-cyber-neon-orange"
                : response.overall === "cancelling"
                  ? "border-cyber-neon-orange/60 bg-cyber-neon-orange/10 text-cyber-neon-orange"
                  : response.overall === "cancelled"
                    ? "border-cyber-border-subtle bg-cyber-bg-tertiary text-cyber-text-muted"
                    : "border-cyber-neon-pink bg-cyber-neon-pink/10 text-cyber-neon-pink"
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
