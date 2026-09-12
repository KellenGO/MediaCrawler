import { useMemo, useState } from "react";
import { AlertTriangle, Bookmark, RefreshCw, ShieldCheck } from "lucide-react";
import { ResultTabs } from "@/components/search/ResultTabs";
import { useBookmarks } from "@/hooks/useBookmarks";
import { useFavorites } from "@/hooks/useFavorites";
import type { PlatformSlug } from "@/types/search";
import { PLATFORM_COLORS, PLATFORM_LABELS, STATUS_LABELS } from "@/types/search";

const PLATFORMS: PlatformSlug[] = ["xhs", "douyin", "bilibili", "zhihu"];

function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : "收藏夹同步失败，请稍后重试。";
}

export function FavoritesPage({ onNavigateAccounts }: { onNavigateAccounts: () => void }) {
  const remote = useFavorites();
  const library = useBookmarks();
  const [selected, setSelected] = useState<Set<PlatformSlug>>(() => new Set(PLATFORMS));
  const data = remote.data;
  const fetchedAt = useMemo(() => Object.fromEntries(PLATFORMS.map((p) => [p, data?.completed_at ?? null])), [data]);
  const toggle = (platform: PlatformSlug) => setSelected((before) => {
    const next = new Set(before);
    if (next.has(platform) && next.size > 1) next.delete(platform); else next.add(platform);
    return next;
  });

  return <div className="py-8">
    <section className="relative overflow-hidden rounded-[22px] border border-cyber-border-subtle bg-cyber-bg-secondary px-5 py-6 sm:px-7">
      <div className="absolute -right-8 -top-12 h-40 w-40 rounded-full bg-brand/10 blur-3xl" />
      <div className="relative flex flex-wrap items-end justify-between gap-5">
        <div className="max-w-2xl">
          <div className="mb-3 flex items-center gap-2 text-xs font-semibold tracking-[0.16em] text-brand-strong">
            <Bookmark className="h-4 w-4" /> PERSONAL LIBRARY
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-cyber-text-primary sm:text-[30px]">跨平台收藏</h1>
          <p className="mt-2 max-w-xl text-sm leading-6 text-cyber-text-secondary">读取已登录账号最近的收藏内容，统一筛选、导出，也可以保存到本地并添加备注。</p>
        </div>
        <button type="button" disabled={remote.busy || !selected.size}
          onClick={() => void remote.sync([...selected])}
          className="inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2.5 text-sm font-semibold text-white shadow-[0_8px_22px_rgba(76,164,220,0.22)] transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-50">
          <RefreshCw className={`h-4 w-4 ${remote.busy ? "animate-spin" : ""}`} />
          {remote.busy ? "正在同步…" : data ? "重新同步" : "同步收藏夹"}
        </button>
      </div>
      <div className="relative mt-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {PLATFORMS.map((platform) => {
          const active = selected.has(platform);
          const info = data?.platforms[platform];
          return <button key={platform} type="button" aria-pressed={active} onClick={() => toggle(platform)}
            className={`rounded-xl border p-3 text-left transition ${active ? "border-brand/50 bg-brand-soft" : "border-cyber-border-subtle bg-cyber-bg-primary opacity-60"}`}>
            <span className="flex items-center gap-2 text-sm font-semibold text-cyber-text-primary">
              <i className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: PLATFORM_COLORS[platform] }} />{PLATFORM_LABELS[platform]}
            </span>
            <span className="mt-1 block text-xs text-cyber-text-muted">
              {info ? `${STATUS_LABELS[info.status]} · ${info.result_count} 条` : active ? "等待同步" : "本次跳过"}
            </span>
          </button>;
        })}
      </div>
    </section>

    <div className="mt-4 flex items-start gap-2 rounded-xl border border-cyber-border-subtle bg-cyber-bg-secondary px-4 py-3 text-xs text-cyber-text-muted">
      <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-ok" />
      <span>每个平台单次最多读取 20 条收藏，先显示列表，再逐条补充可获取的指标；详情指标缓存 6 小时。平台未提供的浏览量等数据可能仍缺失；“万”“万+”等展示值换算后为近似计数。不会添加、删除或移动平台中的收藏。</span>
    </div>

    {data && <div className="mt-3 space-y-1 text-xs text-cyber-text-muted" aria-live="polite">
      {PLATFORMS.filter((platform) => platform !== "douyin").map((platform) => {
        const rows = data.results.filter((item) => item.platform === platform);
        if (!rows.length) return null;
        const checked = rows.filter((item) => item.metrics_status === "complete" || item.metrics_status === "partial");
        const unavailable = rows.filter((item) => item.metrics_status === "unavailable").length;
        const failed = rows.filter((item) => item.metrics_status === "failed").length;
        const timestamps = checked.flatMap((item) => item.metrics_updated_at ? [item.metrics_updated_at] : []);
        return <p key={platform}>{PLATFORM_LABELS[platform]}：已读取详情指标 {checked.length}/{rows.length}
          {unavailable > 0 && ` · ${unavailable} 条暂不可补全`}
          {failed > 0 && ` · ${failed} 条补全未完成`}
          {checked.some((item) => item.metrics_approximate?.length) && " · 含平台近似计数"}
          {timestamps.length > 0 && ` · 最早采集于 ${new Date(Math.min(...timestamps) * 1000).toLocaleString()}`}
        </p>;
      })}
    </div>}

    {remote.error && <div role="alert" className="mt-4 flex items-center gap-2 rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-sm text-danger">
      <AlertTriangle className="h-4 w-4" />{errorMessage(remote.error)}
    </div>}

    {data && Object.entries(data.platforms).some(([, info]) => info && !["succeeded", "empty", "running", "pending"].includes(info.status)) &&
      <div className="mt-4 rounded-xl border border-warn/30 bg-warn-soft px-4 py-3 text-xs text-warn">
        {Object.entries(data.platforms).filter(([, info]) => info && !["succeeded", "empty"].includes(info.status)).map(([platform, info]) =>
          <p key={platform}>{PLATFORM_LABELS[platform as PlatformSlug]}：{info?.error_summary || STATUS_LABELS[info!.status]}</p>)}
        <button type="button" className="mt-2 underline" onClick={onNavigateAccounts}>检查账号登录状态</button>
      </div>}

    {data ? <ResultTabs results={data.results} overall={data.overall} jobId={data.job_id}
      platforms={Object.keys(data.platforms) as PlatformSlug[]} library={library} fetchedAt={fetchedAt} />
      : !remote.busy && <div className="py-20 text-center text-sm text-cyber-text-muted">选择平台后同步，四处散落的收藏会汇到这里。</div>}
  </div>;
}
