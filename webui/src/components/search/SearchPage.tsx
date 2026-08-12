import { useCallback } from "react";
import { AlertTriangle, RotateCcw, Loader2, UserCog } from "lucide-react";
import { SearchBar } from "./SearchBar";
import { PlatformStatus } from "./PlatformStatus";
import { ResultTabs } from "./ResultTabs";
import { useAggregateSearch } from "@/hooks/useAggregateSearch";
import type { PlatformSlug } from "@/types/search";
import { PLATFORM_LABELS, PLATFORM_ICONS } from "@/types/search";

interface SearchPageProps {
  onNavigateConsole?: () => void;
  onNavigateAccounts?: () => void;
}

export function SearchPage({ onNavigateConsole, onNavigateAccounts }: SearchPageProps) {
  const {
    startSearch,
    cancel,
    reset,
    isCreating,
    isCancelling,
    createError,
    pollError,
    jobResponse,
    overall,
    searchedPlatforms,
  } = useAggregateSearch();

  const handleSearch = useCallback(
    (keyword: string, platforms: PlatformSlug[]) => {
      startSearch(keyword, platforms, 10);
    },
    [startSearch]
  );

  const handleGoAccounts = useCallback(() => {
    onNavigateAccounts?.();
  }, [onNavigateAccounts]);

  const isSearching = overall === "running" || isCreating;
  const isCancellingState = overall === "cancelling" || isCancelling;
  const isCancelled = overall === "cancelled";
  const hasError = !!createError || !!pollError;
  const isTerminal = overall === "completed" || overall === "partial" || overall === "failed" || overall === "cancelled";

  // Type-safe error extractor for axios errors (including 422 detail arrays)
  function getErrorMessage(err: unknown): string {
    const e = err as { response?: { status?: number; data?: { detail?: unknown } }; message?: string };
    if (e?.response?.status === 409) return "已有任务正在运行，请等待完成后再试。";
    if (e?.response?.status === 404) return "任务已失效，请重新搜索。";
    const detail = e?.response?.data?.detail;
    if (Array.isArray(detail)) {
      return detail.map((d: { msg?: string }) => d.msg || "").join("; ") || "请求参数无效";
    }
    return (typeof detail === "string" ? detail : null) || e?.message || "请求失败，请重试。";
  }

  return (
    <div className="flex flex-col items-center px-4 py-6 h-full overflow-y-auto">
      <div className="text-center mb-6">
        <h1 className="text-2xl font-mono font-bold text-cyber-text-primary">
          中文社交平台聚合搜索
        </h1>
        <p className="mt-2 text-sm font-mono text-cyber-text-muted">
          同时搜索 小红书 · 抖音 · B站 · 知乎
        </p>
        {onNavigateConsole && (
          <button
            onClick={onNavigateConsole}
            className="mt-2 text-xs font-mono text-cyber-text-muted hover:text-cyber-neon-cyan transition-colors underline underline-offset-2"
          >
            高级功能 → 原始爬虫控制台
          </button>
        )}
      </div>

      <SearchBar
        onSearch={handleSearch}
        isSearching={isSearching || isCancellingState}
        onCancel={cancel}
        isCancelling={isCancellingState}
        onReset={reset}
      />

      <PlatformStatus response={jobResponse} />

      {/* Cancelling */}
      {isCancellingState && (
        <div className="mt-4 flex items-center gap-2 px-4 py-2 rounded-lg border border-cyber-neon-orange/50 bg-cyber-neon-orange/10 text-cyber-neon-orange font-mono text-sm">
          <Loader2 className="w-4 h-4 animate-spin" />
          正在取消搜索...
        </div>
      )}

      {/* Cancelled */}
      {isCancelled && (
        <div className="mt-6 text-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-cyber-neon-orange/50 bg-cyber-neon-orange/10 text-cyber-neon-orange font-mono text-sm">
            ⏹ 搜索已取消
          </div>
        </div>
      )}

      {/* Error */}
      {(createError || pollError) && (
        <div className="mt-4 flex items-center gap-3 px-4 py-3 rounded-lg border border-cyber-neon-pink/50 bg-cyber-neon-pink/10 text-cyber-neon-pink font-mono text-sm max-w-2xl w-full">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span className="flex-1">{getErrorMessage(createError || pollError)}</span>
          <button onClick={reset} className="flex-shrink-0 flex items-center gap-1 px-2 py-1 rounded border border-cyber-neon-pink/50 hover:bg-cyber-neon-pink/20 text-xs transition-all">
            <RotateCcw className="w-3 h-3" />重试
          </button>
        </div>
      )}

      {/* Idle */}
      {overall === "idle" && !hasError && (
        <div className="mt-16 text-center">
          <div className="text-5xl mb-4">🔍</div>
          <p className="text-sm font-mono text-cyber-text-muted">
            输入关键词，选择平台，开始跨平台搜索
          </p>
        </div>
      )}

      {/* Failed */}
      {overall === "failed" && jobResponse && (
        <div className="mt-6 w-full max-w-2xl">
          <div className="text-center mb-4 px-4 py-2 rounded-lg border border-cyber-neon-pink/50 bg-cyber-neon-pink/10 text-cyber-neon-pink font-mono text-sm">
            <AlertTriangle className="w-4 h-4 inline mr-2" />所有平台搜索失败
          </div>
          {Object.entries(jobResponse.platforms).map(([p, info]) => (
            <div key={p} className="flex items-center justify-between px-3 py-2 mb-1 rounded bg-cyber-bg-tertiary border border-cyber-border-subtle text-sm font-mono">
              <span className="text-cyber-text-muted">
                {PLATFORM_ICONS[p as PlatformSlug]} {PLATFORM_LABELS[p as PlatformSlug] || p}: {info.error_summary || info.status}
              </span>
              {info.status === "login_required" && (
                <button onClick={handleGoAccounts}
                  className="px-3 py-1 rounded bg-cyber-neon-cyan/20 border border-cyber-neon-cyan/50 text-cyber-neon-cyan hover:bg-cyber-neon-cyan/30 text-xs transition-all">
                  <UserCog className="w-3 h-3 inline mr-1" />前往账号设置
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Partial */}
      {overall === "partial" && jobResponse && (
        <div className="mt-4 w-full max-w-2xl px-3 py-2 rounded-lg border border-cyber-neon-orange/50 bg-cyber-neon-orange/10 text-cyber-neon-orange font-mono text-xs">
          ⚠ 部分平台失败: {Object.entries(jobResponse.platforms)
            .filter(([, i]) => !["succeeded", "empty"].includes(i.status))
            .map(([p, i]) => `${PLATFORM_LABELS[p as PlatformSlug] || p}(${i.error_summary || i.status})`)
            .join(", ")}
        </div>
      )}

      {/* Results */}
      {jobResponse && overall !== "failed" && (
        <div className="w-full max-w-3xl mt-4">
          <p className="text-xs font-mono text-cyber-text-muted mb-2">
            搜索: <span className="text-cyber-text-primary">{jobResponse.keyword}</span>
            {isTerminal && jobResponse.completed_at && (
              <span className="ml-3">完成于 {new Date(jobResponse.completed_at).toLocaleTimeString("zh-CN")}</span>
            )}
            {!isTerminal && <span className="ml-3 text-cyber-neon-cyan animate-pulse">搜索中...</span>}
          </p>

          {Object.entries(jobResponse.platforms).some(([, i]) => i.status === "login_required") && (
            <div className="mb-3 p-3 rounded-lg border border-cyber-neon-orange/30 bg-cyber-neon-orange/5">
              <p className="text-xs font-mono text-cyber-neon-orange mb-2">以下平台需要先登录：</p>
              <div className="flex flex-wrap gap-2">
                <button onClick={handleGoAccounts}
                  className="px-3 py-1.5 rounded-lg bg-cyber-neon-orange/10 border border-cyber-neon-orange/40 text-cyber-neon-orange hover:bg-cyber-neon-orange/20 text-xs font-mono transition-all">
                  <UserCog className="w-3 h-3 inline mr-1" />
                  前往账号设置
                </button>
              </div>
            </div>
          )}

          <ResultTabs
            results={jobResponse.results}
            overall={jobResponse.overall}
            platforms={searchedPlatforms || Object.keys(jobResponse.platforms) as PlatformSlug[]}
          />
        </div>
      )}
    </div>
  );
}
