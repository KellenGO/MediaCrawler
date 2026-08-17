import { useState, useMemo, useEffect } from "react";
import type { PlatformSlug, UnifiedSearchResult } from "@/types/search";
import type { SearchSortMode } from "@/lib/searchExperience";
import { resolveActiveTab, sortResults } from "@/lib/searchExperience";
import { ResultCard } from "./ResultCard";

interface ResultTabsProps {
  results: UnifiedSearchResult[];
  keyword?: string;
  overall: string;
  platforms: PlatformSlug[];
  sortMode?: SearchSortMode;
  onSortModeChange?: (mode: SearchSortMode) => void;
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
  sortMode = "default",
  onSortModeChange,
}: ResultTabsProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("all");

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

  // 先按当前标签筛选，再按所选模式排序（纯前端计算，不发任何请求）。
  const filteredResults = useMemo(() => {
    const scoped = effectiveTab === "all" ? results : results.filter((r) => r.platform === effectiveTab);
    return sortResults(scoped, sortMode, keyword);
  }, [results, effectiveTab, sortMode, keyword]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: results.length };
    for (const r of results) {
      c[r.platform] = (c[r.platform] || 0) + 1;
    }
    return c;
  }, [results]);

  if (results.length === 0) {
    if (overall === "running") {
      return (
        <div className="text-center py-12">
          <div className="inline-block animate-dsh-spin rounded-full h-8 w-8 border-2 border-brand border-t-transparent" />
          <p className="mt-4 text-sm text-cyber-text-muted">
            正在搜索中...
          </p>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="mt-6">
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
      </div>

      {/* 结果卡片 */}
      <div className="flex flex-col gap-3">
        {filteredResults.map((result, i) => (
          <ResultCard key={`${result.platform}-${result.content_id}-${i}`} result={result} />
        ))}
      </div>

      {filteredResults.length === 0 && (
        <p className="text-center py-10 text-sm text-cyber-text-muted">
          该平台暂无结果
        </p>
      )}
    </div>
  );
}
