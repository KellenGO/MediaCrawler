import { useCallback, useState } from "react";
import { AlertTriangle, RotateCcw, Loader2, UserCog, RefreshCw } from "lucide-react";
import { SearchBar } from "./SearchBar";
import { PlatformStatus } from "./PlatformStatus";
import { ResultTabs } from "./ResultTabs";
import { useSearchExperience } from "@/hooks/useSearchExperience";
import { usePlatformLimits } from "@/hooks/usePlatformLimits";
import type { PlatformSlug } from "@/types/search";
import { PLATFORM_LABELS } from "@/types/search";
import type { SearchHistoryItem } from "@/lib/searchExperience";

interface SearchPageProps {
  onNavigateConsole?: () => void;
  onNavigateAccounts?: () => void;
}

/**
 * Round 14 搜索页：主体从搜索框开始，下面直接呈现状态与搜索结果。
 * 业务状态逻辑（Round 12–13）原样保留：快照 / 单平台重试合并 / 取消 /
 * 历史 / 任务恢复 —— 本组件只改布局与视觉。
 */
export function SearchPage({ onNavigateAccounts }: SearchPageProps) {
  // Round 15: 每个平台独立搜索数量（展示用；搜索请求由 useSearchExperience 读取）。
  const { limits } = usePlatformLimits();
  const {
    displayJobResponse,
    showingStaleSnapshot,
    liveHint,
    refreshing,
    retryingPlatform,
    retryErrors,
    cancelledNotice,
    cancelError,
    sortMode,
    setSortMode,
    history,
    removeHistory,
    clearHistory,
    updatePlatformPref,
    platformPref,
    handleFullSearch,
    handleRefresh,
    handleRetry,
    handleCancel,
    handleReset,
    isCancelling,
    createError,
    pollError,
    busy,
  } = useSearchExperience();

  // 受控输入：初始平台选择来自 localStorage 偏好（至少一个平台）。
  const [keyword, setKeyword] = useState("");
  const [selectedPlatforms, setSelectedPlatforms] = useState<Set<PlatformSlug>>(
    () => new Set(platformPref)
  );

  // 平台选择变化：同步受控控件 + 立即持久化偏好（两次点击间不丢）。
  const handlePlatformsChange = useCallback(
    (platforms: PlatformSlug[]) => {
      setSelectedPlatforms(new Set(platforms));
      updatePlatformPref(platforms);
    },
    [updatePlatformPref]
  );

  const handleGoAccounts = useCallback(() => {
    onNavigateAccounts?.();
  }, [onNavigateAccounts]);

  // 取消：只发起取消请求；"已取消"提示由 hook 观察真实 job 终态驱动。
  const handleCancelClick = useCallback(() => {
    void handleCancel();
  }, [handleCancel]);

  const handleFullSearchLocal = useCallback(
    (kw: string, platforms: PlatformSlug[]) => {
      void handleFullSearch(kw, platforms);
    },
    [handleFullSearch]
  );

  const handleResetLocal = useCallback(() => {
    handleReset();
  }, [handleReset]);

  // 历史回放：先同步可见控件（关键词/平台选择/平台偏好），再用 item 参数
  // 直接发起搜索 —— 不依赖 state 更新完成后的读取；取消提示由新任务的
  // search_start 清除。
  // 【组件接线，人工验收】即使搜索 POST 失败，可见平台选择与 localStorage
  // 偏好也保持历史项的平台（用户已主动切换搜索条件）；只发起一次搜索由
  // hook 的 busy + taskInFlight 双 guard 保证。
  const handleHistoryClickLocal = useCallback(
    (item: SearchHistoryItem) => {
      setKeyword(item.keyword);
      setSelectedPlatforms(new Set(item.platforms));
      updatePlatformPref(item.platforms); // 同步持久化偏好（刷新后保持）
      void handleFullSearch(item.keyword, item.platforms);
    },
    [handleFullSearch, updatePlatformPref]
  );

  const isCancellingState = isCancelling;
  const hasError = !!createError || !!pollError;
  const isTerminal =
    displayJobResponse?.overall === "completed" ||
    displayJobResponse?.overall === "partial" ||
    displayJobResponse?.overall === "failed" ||
    displayJobResponse?.overall === "cancelled";

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

  const showInitialIdle = !displayJobResponse && !busy && !hasError;
  const showInitialLoading = !displayJobResponse && busy && !hasError;

  // Round 15.1: 本次搜索中真正返回 login_required 的平台。
  // 只取 displayJobResponse.platforms 的 key 并按 status 筛选，不解析
  // error_summary、不根据顶部账号状态推断。显隐判断与平台标签共用同一数组。
  const loginRequiredPlatforms: PlatformSlug[] = displayJobResponse
    ? (Object.keys(displayJobResponse.platforms) as PlatformSlug[]).filter(
        (p) => displayJobResponse.platforms[p].status === "login_required"
      )
    : [];

  return (
    <div className="pt-7 pb-4">
      {/* 搜索面板（含聚焦浮层：最近搜索 / 推荐搜索） */}
      <SearchBar
        keyword={keyword}
        onKeywordChange={setKeyword}
        selectedPlatforms={selectedPlatforms}
        onPlatformsChange={handlePlatformsChange}
        onSearch={handleFullSearchLocal}
        isSearching={busy}
        onCancel={handleCancelClick}
        isCancelling={isCancellingState}
        onReset={handleResetLocal}
        history={history}
        onHistoryClick={handleHistoryClickLocal}
        onHistoryRemove={removeHistory}
        onHistoryClear={clearHistory}
        limits={limits}
      />

      {/* 平台搜索状态（统一浅色状态卡） */}
      <PlatformStatus
        response={displayJobResponse ?? undefined}
        onRetry={handleRetry}
        retryingPlatform={retryingPlatform}
        retryDisabled={busy}
      />

      {/* Cancelling */}
      {isCancellingState && (
        <div className="mt-4 flex items-center gap-2 px-4 py-2.5 rounded-xl border border-warn/40 bg-warn-soft text-warn text-sm w-fit">
          <Loader2 className="w-4 h-4 animate-spin" />
          正在取消搜索...
        </div>
      )}

      {/* 取消失败（Round 13）：固定安全文案，绝不显示 axios 500 原文；
          任务仍在运行（轮询继续），提供"再次取消"，不清除旧结果，
          不错误显示"已取消"。 */}
      {cancelError && (
        <div className="mt-4 flex items-center gap-3 px-4 py-3 rounded-xl border border-warn/50 bg-warn-soft text-warn text-sm max-w-2xl w-full">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span className="flex-1">{cancelError}</span>
          <button
            onClick={handleCancelClick}
            disabled={isCancellingState}
            className="flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg border border-warn/50 hover:bg-warn/10 text-xs transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Loader2 className="w-3 h-3" />再次取消
          </button>
        </div>
      )}

      {/* Cancelled（取消保留旧结果，提示由真实终态驱动） */}
      {cancelledNotice && !busy && !createError && !cancelError && (
        <div className="mt-6 text-center">
          <div className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-warn/40 bg-warn-soft text-warn text-sm">
            ⏹ 搜索已取消，保留上次结果
          </div>
        </div>
      )}

      {/* Error */}
      {(createError || pollError) && (
        <div className="mt-4 flex items-center gap-3 px-4 py-3 rounded-xl border border-danger/40 bg-danger-soft text-danger text-sm max-w-2xl w-full">
          <AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span className="flex-1">{getErrorMessage(createError || pollError)}</span>
          <button onClick={handleReset} className="flex-shrink-0 flex items-center gap-1 px-2.5 py-1 rounded-lg border border-danger/40 hover:bg-danger/10 text-xs transition-all">
            <RotateCcw className="w-3 h-3" />重试
          </button>
        </div>
      )}

      {/* Initial idle */}
      {showInitialIdle && (
        <div className="mt-16 text-center">
          <p className="text-sm text-cyber-text-muted">
            输入关键词，选择平台，开始跨平台搜索
          </p>
        </div>
      )}

      {/* Initial loading（首次搜索，无旧结果可展示） */}
      {showInitialLoading && (
        <div className="mt-16 text-center">
          <div className="inline-block animate-dsh-spin rounded-full h-8 w-8 border-2 border-brand border-t-transparent" />
          <p className="mt-4 text-sm text-cyber-text-muted">
            正在搜索中...
          </p>
        </div>
      )}

      {/* Failed (all platforms) */}
      {displayJobResponse && displayJobResponse.overall === "failed" && (
        <div className="mt-6 w-full max-w-2xl">
          <div className="text-center mb-3 px-4 py-2 rounded-xl border border-danger/40 bg-danger-soft text-danger text-sm">
            <AlertTriangle className="w-4 h-4 inline mr-2" />所有平台搜索失败
          </div>
          {Object.entries(displayJobResponse.platforms).map(([p, info]) => (
            <div key={p} className="flex items-center justify-between px-3.5 py-2.5 mb-1.5 rounded-lg bg-cyber-bg-secondary border border-cyber-border-subtle text-sm">
              <span className="text-cyber-text-secondary">
                {PLATFORM_LABELS[p as PlatformSlug] || p}: {info.error_summary || info.status}
              </span>
              {info.status === "login_required" && (
                <button onClick={handleGoAccounts}
                  className="px-3 py-1 rounded-lg bg-brand-soft border border-brand/40 text-brand-strong hover:bg-brand/10 text-xs transition-all">
                  <UserCog className="w-3 h-3 inline mr-1" />前往账号设置
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Partial */}
      {displayJobResponse && displayJobResponse.overall === "partial" && (
        <div className="mt-4 w-full max-w-2xl px-3.5 py-2 rounded-xl border border-warn/40 bg-warn-soft text-warn text-xs">
          ⚠ 部分平台失败: {Object.entries(displayJobResponse.platforms)
            .filter(([, i]) => !["succeeded", "empty"].includes(i.status))
            .map(([p, i]) => `${PLATFORM_LABELS[p as PlatformSlug] || p}(${i.error_summary || i.status})`)
            .join(", ")}
        </div>
      )}

      {/* Results（全宽布局，无右侧栏） */}
      {displayJobResponse && displayJobResponse.overall !== "failed" && (
        <div className={`w-full mt-4 transition-opacity ${refreshing || showingStaleSnapshot ? "opacity-60" : "opacity-100"}`}>
          {(liveHint || refreshing) && (
            <div className="mb-3 flex items-center gap-2 px-3.5 py-2 rounded-xl border border-brand/40 bg-brand-soft text-brand-strong text-xs w-fit">
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              {liveHint ?? "正在更新，暂时显示上次结果"}
            </div>
          )}

          <div className="flex items-center justify-between gap-3 mb-2">
            <p className="text-xs text-cyber-text-muted">
              搜索: <span className="text-cyber-text-primary">{displayJobResponse.keyword}</span>
              {isTerminal && displayJobResponse.completed_at && (
                <span className="ml-3">完成于 {new Date(displayJobResponse.completed_at).toLocaleTimeString("zh-CN")}</span>
              )}
              {!isTerminal && <span className="ml-3 text-brand-strong animate-pulse">搜索中...</span>}
            </p>
            {isTerminal && (
              <button
                type="button"
                onClick={handleRefresh}
                disabled={busy}
                className="flex-shrink-0 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-cyber-border-subtle text-xs text-cyber-text-secondary hover:text-brand-strong hover:border-brand/50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                aria-label="重新搜索"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                重新搜索
              </button>
            )}
          </div>

          {/* 单平台重试失败提示（保留旧结果，仅显示安全摘要） */}
          {Object.entries(retryErrors).map(([platform, message]) => (
            <div key={platform} className="mb-2 px-3.5 py-2 rounded-xl border border-danger/30 bg-danger-soft text-danger text-xs">
              更新失败：{PLATFORM_LABELS[platform as PlatformSlug] || platform} {message}
            </div>
          ))}

          {loginRequiredPlatforms.length > 0 && (
            <div className="mb-3 p-3 rounded-xl border border-warn/30 bg-warn-soft/60">
              <p className="text-xs text-warn mb-2">以下平台需要先登录：</p>
              <div className="flex flex-wrap gap-2 mb-2">
                {loginRequiredPlatforms.map((p) => (
                  <span
                    key={p}
                    className="px-2.5 py-1 rounded-full bg-warn-soft border border-warn/40 text-warn text-[11.5px] font-medium"
                  >
                    {PLATFORM_LABELS[p] || p}
                  </span>
                ))}
              </div>
              <button onClick={handleGoAccounts}
                className="px-3 py-1.5 rounded-lg bg-warn-soft border border-warn/40 text-warn hover:bg-warn/10 text-xs transition-all">
                <UserCog className="w-3 h-3 inline mr-1" />
                前往设置
              </button>
            </div>
          )}

          <ResultTabs
            results={displayJobResponse.results}
            keyword={displayJobResponse.keyword}
            overall={displayJobResponse.overall}
            platforms={Object.keys(displayJobResponse.platforms) as PlatformSlug[]}
            sortMode={sortMode}
            onSortModeChange={setSortMode}
          />
        </div>
      )}
    </div>
  );
}
