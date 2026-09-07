import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PLATFORM_LABELS, STATUS_LABELS, type PlatformSlug, type PlatformStatus } from "@/types/search";
import { TOOL_BUTTON } from "./ResultTools";

interface Duration { samples: number; mean_ms: number | null; median_ms: number | null; p95_ms: number | null }
interface PlatformStatistics {
  requests: number; worker_runs: number; successes: number; success_samples: number;
  success_rate: number | null; cache_hits: number; cache_hit_rate: number | null;
  cooldown_skips: number; cancelled_runs: number; fallback_samples: number; fallback_rate: number | null;
  failures: Partial<Record<PlatformStatus, number>>;
  first_result_ms: Duration; total_ms: Duration; spawn_ms: Duration; browser_launch_ms: Duration;
}
interface Statistics {
  max_jobs: number; job_count: number; since: string | null; job_total_ms: Duration;
  platforms: Record<PlatformSlug, PlatformStatistics>;
}
const percent = (value: number | null) => value === null ? "暂无样本" : `${(value * 100).toFixed(0)}%`;
const seconds = (value: number | null) => value === null ? "—" : `${(value / 1000).toFixed(2)} 秒`;

function StatisticsPanel({ refreshKey }: { refreshKey: string }) {
  const query = useQuery<Statistics>({
    queryKey: ["search-statistics"],
    queryFn: async ({ signal }) => {
      const response = await fetch("/api/search/statistics", { signal });
      if (!response.ok) throw new Error("Statistics unavailable");
      const data = await response.json();
      if (!data.platforms || typeof data.job_count !== "number") throw new Error("Invalid statistics");
      return data;
    },
    refetchInterval: () => document.visibilityState === "hidden" ? false : 5000,
    retry: false,
  });
  const { refetch } = query;
  useEffect(() => { void refetch(); }, [refreshKey, refetch]);
  return <section id="search-statistics" aria-label="最近搜索统计" className="mt-3 rounded-xl border border-cyber-border-subtle bg-cyber-bg-secondary p-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h2 className="text-sm font-semibold text-cyber-text-primary">最近搜索统计</h2>
      <button type="button" className={TOOL_BUTTON} disabled={query.isFetching} onClick={() => void refetch()}>刷新统计</button>
    </div>
    {query.isPending && <p className="mt-2 text-xs text-cyber-text-muted">正在读取统计…</p>}
    {query.isError && <p role="alert" className="mt-2 text-xs text-warn">统计暂时无法读取，可点击刷新重试。{query.data && "以下保留上次统计。"}</p>}
    {query.data && <>
      <p className="mt-2 text-xs text-cyber-text-muted">
        本次服务运行最近 {query.data.job_count}/{query.data.max_jobs} 次已结束搜索，重启服务后清空。
        {query.data.job_count === 0 ? "完成搜索后会在这里显示数据。" : ` 整次搜索耗时中位数 ${seconds(query.data.job_total_ms.median_ms)}。`}
      </p>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {(Object.entries(query.data.platforms) as [PlatformSlug, PlatformStatistics][]).map(([platform, info]) => <div key={platform}
          className="min-w-0 rounded-lg border border-cyber-border-subtle bg-cyber-bg-primary p-3 text-xs text-cyber-text-secondary">
          <h3 className="font-semibold text-cyber-text-primary mb-2">{PLATFORM_LABELS[platform]}</h3>
          <p>参与 {info.requests} 次 · 实际搜索 {info.worker_runs} 次</p>
          <p className="mt-1">成功率 {percent(info.success_rate)}（{info.successes}/{info.success_samples}）</p>
          <p className="mt-1">缓存命中 {percent(info.cache_hit_rate)}（{info.cache_hits} 次）</p>
          <p className="mt-1">备用路径 {percent(info.fallback_rate)}（{info.fallback_samples} 个样本）</p>
          <p className="mt-1">冷却拦截 {info.cooldown_skips} 次 · 取消 {info.cancelled_runs} 次</p>
          <dl className="mt-3 space-y-1">
            <div><dt>首条结果 · 中位数 / P95</dt><dd>{seconds(info.first_result_ms.median_ms)} / {seconds(info.first_result_ms.p95_ms)}（{info.first_result_ms.samples} 个样本）</dd></div>
            <div><dt>平台完成 · 中位数 / P95</dt><dd>{seconds(info.total_ms.median_ms)} / {seconds(info.total_ms.p95_ms)}</dd></div>
            <div><dt>取得搜索进程 · 平均</dt><dd>{seconds(info.spawn_ms.mean_ms)}</dd></div>
            <div><dt>浏览器就绪 · 平均</dt><dd>{seconds(info.browser_launch_ms.mean_ms)}</dd></div>
          </dl>
          {Object.keys(info.failures).length > 0 && <p className="mt-2 text-warn">失败原因：{Object.entries(info.failures).map(([status, count]) => `${STATUS_LABELS[status as PlatformStatus] || status} ${count} 次`).join("、")}</p>}
        </div>)}
      </div>
      <p className="mt-3 text-xs text-cyber-text-muted">成功率与平台耗时不计缓存、冷却拦截和取消；无结果也算搜索成功。备用路径只统计有上报的数据。P95 表示约 95% 样本不超过此耗时，少量样本仅供参考。浏览器就绪为请求开始至浏览器就绪的累计时间。整次搜索耗时包含缓存和取消。</p>
    </>}
  </section>;
}

export function SearchStatistics({ refreshKey }: { refreshKey: string }) {
  const [open, setOpen] = useState(false);
  return <div className="mt-3">
    <button type="button" className={TOOL_BUTTON} aria-expanded={open} aria-controls="search-statistics" onClick={() => setOpen(!open)}>
      {open ? "收起搜索统计" : "查看搜索统计"}
    </button>
    {open && <StatisticsPanel refreshKey={refreshKey} />}
  </div>;
}
