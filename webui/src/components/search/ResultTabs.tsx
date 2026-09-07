import { useState, useMemo, useEffect, useRef } from "react";
import type { PlatformSlug, UnifiedSearchResult } from "@/types/search";
import type { SearchSortMode } from "@/lib/searchExperience";
import {
  resolveActiveTab,
  sortResults,
} from "@/lib/searchExperience";
import { ResultCard } from "./ResultCard";
import { BookmarkControl, BookmarkNote, ExportActions, TOOL_BUTTON } from "./ResultTools";
import type { BookmarkLibrary } from "@/hooks/useBookmarks";
import { DEFAULT_FILTERS, exportRows, filterResultGroups, groupKey, resultKey, type ContentFilter, type ResultFilters } from "@/lib/resultTools";

interface ResultTabsProps {
  results: UnifiedSearchResult[];
  keyword?: string;
  overall: string;
  jobId?: string;
  hydrationStatus?: "not_started" | "running" | "completed";
  platforms: PlatformSlug[];
  sortMode?: SearchSortMode;
  onSortModeChange?: (mode: SearchSortMode) => void;
  library?: BookmarkLibrary;
  savedView?: boolean;
  fetchedAt?: Partial<Record<PlatformSlug, string | null>>;
}

type TabKey = "all" | PlatformSlug;

/** Round 14：平台结果标签固定为五个（全部 / 小红书 / 抖音 / B站 / 知乎）。 */
const ALL_TABS: { key: TabKey; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "xhs", label: "小红书" },
  { key: "douyin", label: "抖音" },
  { key: "bilibili", label: "B站" },
  { key: "zhihu", label: "知乎" },
];

const SORT_MODES: { key: SearchSortMode; label: string }[] = [
  { key: "default", label: "综合" },
  { key: "latest", label: "最新" },
  { key: "engagement", label: "互动最多" },
];

export function ResultTabs({
  results,
  keyword = "",
  overall,
  jobId,
  hydrationStatus = "not_started",
  sortMode = "default",
  onSortModeChange,
  library,
  savedView = false,
  fetchedAt = {},
}: ResultTabsProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("all");
  const [filters, setFilters] = useState<ResultFilters>({ ...DEFAULT_FILTERS });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [exportOpen, setExportOpen] = useState(false);
  const nowMs = useMemo(() => Date.now(), [results, filters]);

  // 五个固定标签始终可见；合法性判断仍走生产纯函数 resolveActiveTab，
  // 当激活标签不在可见集合时回退到"全部"（lib 内已直接测试）。
  const visibleTabs = ALL_TABS;
  const effectiveTab = resolveActiveTab<TabKey>(
    activeTab,
    visibleTabs.map(t => t.key),
    "all"
  );

  // 【组件 state 接线，人工验证】真正重置 activeTab state（而非仅钳制显示）：
  // - 失效时通过 effect 在渲染后 setActiveTab("all")，避免 render 阶段 setState；
  // - state 已变为 "all" 后，平台重新出现时不会自动恢复失效的旧标签。
  useEffect(() => {
    if (effectiveTab !== activeTab) {
      setActiveTab("all");
    }
  }, [activeTab, effectiveTab]);

  const hydrationOrderRef = useRef<{ signature: string; keys: string[] } | null>(null);
  useEffect(() => setSelected(new Set()), [jobId, effectiveTab, filters]);
  useEffect(() => setExportOpen(false), [jobId]);

  // 先按当前标签筛选，再按所选模式排序（纯前端计算，不发任何请求）。
  const filteredResults = useMemo(() => {
    const scoped = filterResultGroups(results, filters, nowMs, effectiveTab);
    const sorted = sortResults(scoped, sortMode, keyword);
    const resultKey = (r: UnifiedSearchResult) => `${r.platform}|${r.content_id}`;
    const signature = [
      jobId ?? "",
      effectiveTab,
      sortMode,
      keyword,
      JSON.stringify(filters),
      scoped.map(resultKey).sort().join(","),
    ].join("\u0001");
    if (hydrationStatus === "not_started") {
      hydrationOrderRef.current = { signature, keys: sorted.map(resultKey) };
      return sorted;
    }
    if (hydrationOrderRef.current?.signature !== signature) {
      hydrationOrderRef.current = { signature, keys: sorted.map(resultKey) };
      return sorted;
    }
    const byKey = new Map(sorted.map((result) => [resultKey(result), result]));
    return hydrationOrderRef.current.keys
      .map((key) => byKey.get(key))
      .filter((result): result is UnifiedSearchResult => Boolean(result));
  }, [results, effectiveTab, sortMode, keyword, hydrationStatus, jobId, filters, nowMs]);

  const counts = useMemo(() => {
    const matching = filterResultGroups(results, filters, nowMs);
    const c: Record<string, number> = { all: matching.length };
    for (const r of matching) {
      const sources = r.grouped_sources && r.grouped_sources.length >= 2
        ? r.grouped_sources
        : [r];
      for (const source of sources) {
        c[source.platform] = (c[source.platform] || 0) + 1;
      }
    }
    return c;
  }, [results, filters, nowMs]);

  const selectedResults = filteredResults.filter((result) => selected.has(groupKey(result)));
  const bookmarks = new Map((library?.items || []).map((item) => [resultKey(item.result), item]));
  const rows = exportRows(selectedResults.length ? selectedResults : filteredResults, (source) => {
    const saved = bookmarks.get(resultKey(source));
    return { fetchedAt: savedView ? saved?.fetchedAt ?? null : fetchedAt[source.platform] ?? null,
      savedAt: saved?.savedAt ?? null, note: saved?.note ?? "" };
  });
  const allSelected = filteredResults.length > 0 && selectedResults.length === filteredResults.length;
  const selectClass = "rounded-lg border border-cyber-border-subtle bg-cyber-bg-secondary px-2.5 py-2 text-xs text-cyber-text-primary focus:outline-none focus:ring-2 focus:ring-brand/40";

  return (
    <div className="mt-6">
      <div className="mb-4 rounded-xl border border-cyber-border-subtle bg-cyber-bg-secondary p-3">
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-cyber-text-muted">发布时间
            <select aria-label="发布时间筛选" className={selectClass} value={filters.days}
              onChange={(event) => setFilters({ ...filters, days: Number(event.target.value) as 0 | 7 | 30 })}>
              <option value={0}>全部时间</option><option value={7}>近 7 天</option><option value={30}>近 30 天</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-xs text-cyber-text-muted">内容类型
            <select aria-label="内容类型筛选" className={selectClass} value={filters.contentType}
              onChange={(event) => setFilters({ ...filters, contentType: event.target.value as ContentFilter })}>
              <option value="all">全部类型</option><option value="video">视频</option><option value="note">图文 / 帖子</option><option value="article">文章 / 回答</option>
            </select>
          </label>
          <input aria-label="结果内关键词" className={`${selectClass} min-w-0 flex-1 basis-48`} maxLength={200}
            placeholder="在标题、作者、摘要中查找" value={filters.query} onChange={(event) => setFilters({ ...filters, query: event.target.value })} />
          <button type="button" className={TOOL_BUTTON} onClick={() => setFilters({ ...DEFAULT_FILTERS })}>清除筛选</button>
        </div>
        <p className="mt-2 text-xs text-cyber-text-muted" role="status">
          {savedView ? "本地收藏" : "当前已返回结果"}中符合条件 {filteredResults.length} 条。仅筛选已有内容，不额外请求平台。{filters.days > 0 && " 日期未知的内容不在此时间范围内。"}
        </p>
      </div>
      {/* 标签栏 + 排序：标签固定五项，宽度不足时自然换行，绝不出现内部滚动条 */}
      <div className="flex items-end justify-between gap-4 flex-wrap border-b border-cyber-border-subtle pb-[13px] mb-4">
        <div className="flex gap-5 flex-wrap overflow-visible" role="tablist" aria-label="结果平台">
          {visibleTabs.map((tab) => {
            const count = counts[tab.key] || 0;
            const active = effectiveTab === tab.key;
            return (
              <button
                key={tab.key}
                role="tab"
                aria-selected={active}
                onClick={() => setActiveTab(tab.key)}
                className={`relative py-1.5 text-[13.5px] whitespace-nowrap transition-colors ${
                  active
                    ? "text-cyber-text-primary font-bold"
                    : "text-cyber-text-muted hover:text-cyber-text-primary"
                }`}
              >
                {tab.label}
                <span className={`ml-1.5 text-[10.5px] ${active ? "text-cyber-text-muted" : "text-cyber-text-muted/70"}`}>
                  {count}
                </span>
                {active && (
                  <span className="absolute left-0 right-0 -bottom-[15px] h-[2px] rounded-full bg-brand" />
                )}
              </button>
            );
          })}
        </div>

        <div className="flex flex-wrap items-center gap-2">
        {onSortModeChange && (
          <div className="flex gap-0.5 rounded-[10px] border border-cyber-border-subtle bg-cyber-bg-secondary p-1" role="group" aria-label="排序方式">
            {SORT_MODES.map((m) => (
              <button
                key={m.key}
                type="button"
                onClick={() => onSortModeChange(m.key)}
                className={`px-2.5 py-1 rounded-[7px] text-[11.5px] transition-colors ${
                  sortMode === m.key
                    ? "bg-brand-soft text-brand-strong font-semibold"
                    : "text-cyber-text-muted hover:text-cyber-text-primary"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        )}
        <button type="button" className={TOOL_BUTTON} aria-expanded={exportOpen} onClick={() => {
          setExportOpen(!exportOpen); setSelected(new Set());
        }}>{exportOpen ? "收起导出" : "导出 / 复制"}</button>
        </div>
      </div>

      {/* 结果卡片 */}
      {exportOpen && <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-cyber-border-subtle bg-cyber-bg-secondary p-3">
        <div className="flex flex-wrap items-center gap-3 text-xs text-cyber-text-muted">
          <label className="flex items-center gap-1.5"><input type="checkbox" aria-label="选择当前全部结果" checked={allSelected}
            disabled={!filteredResults.length} onChange={() => setSelected(allSelected ? new Set() : new Set(filteredResults.map(groupKey)))} />全选当前结果</label>
          <span>{selectedResults.length ? `已选 ${selectedResults.length} 条` : "未勾选时导出当前全部结果"} · 导出 {rows.length} 个来源</span>
        </div>
        <ExportActions rows={rows} keyword={savedView ? "本地收藏" : keyword} />
      </div>}
      <div className="flex flex-col gap-3">
        {filteredResults.map((result) => {
          const key = groupKey(result);
          const bookmark = bookmarks.get(resultKey(result));
          return (
            <div key={key}>
              {exportOpen && <div className="mb-1.5 flex items-center gap-2 px-1">
                <label className="flex min-w-0 items-center gap-1.5 text-xs text-cyber-text-muted">
                  <input type="checkbox" aria-label={`选择 ${result.title}`} checked={selected.has(key)} onChange={() => setSelected((previous) => {
                    const next = new Set(previous); if (next.has(key)) next.delete(key); else next.add(key); return next;
                  })} />选择
                </label>
              </div>}
              <ResultCard result={result} highlightQuery={filters.query || keyword}
                renderBookmark={library ? (source) => <BookmarkControl result={source} library={library} fetchedAt={fetchedAt} /> : undefined} />
              {savedView && bookmark && library && <BookmarkNote bookmark={bookmark} onSave={library.saveNote} />}
            </div>
          );
        })}
      </div>

      {filteredResults.length === 0 && (
        <p className="text-center py-10 text-sm text-cyber-text-muted">
          {overall === "running" && !savedView ? "正在搜索中…" : savedView && !results.length ? "还没有收藏。在搜索结果上点击“收藏”，就能在这里查看。" : "没有符合条件的结果，可清除筛选或切换平台。"}
        </p>
      )}
    </div>
  );
}
