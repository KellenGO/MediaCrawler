import { useState, useMemo, useEffect } from "react";
import type { PlatformSlug, UnifiedSearchResult } from "@/types/search";
import type { SearchSortMode } from "@/lib/searchExperience";
import { resolveActiveTab, sortResults } from "@/lib/searchExperience";
import { ResultCard } from "./ResultCard";

interface ResultTabsProps {
  results: UnifiedSearchResult[];
  overall: string;
  platforms: PlatformSlug[];
  sortMode?: SearchSortMode;
  onSortModeChange?: (mode: SearchSortMode) => void;
}

type TabKey = "all" | PlatformSlug;
const ALL_TABS: { key: TabKey; label: string; icon?: string }[] = [
  { key: "all", label: "全部" },
  { key: "xhs", label: "小红书", icon: "📕" },
  { key: "douyin", label: "抖音", icon: "🎵" },
  { key: "bilibili", label: "B站", icon: "📺" },
  { key: "zhihu", label: "知乎", icon: "💡" },
];

const SORT_MODES: { key: SearchSortMode; label: string }[] = [
  { key: "default", label: "综合" },
  { key: "latest", label: "最新" },
  { key: "engagement", label: "互动最多" },
];

export function ResultTabs({
  results,
  overall,
  platforms,
  sortMode = "default",
  onSortModeChange,
}: ResultTabsProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("all");

  // Only show tabs for the platforms that were actually searched
  const visibleTabs = useMemo(() => {
    const allowed = new Set(platforms);
    return ALL_TABS.filter(t => t.key === "all" || allowed.has(t.key));
  }, [platforms]);

  // 当前标签不在可见集合（如重试后目标平台消失）时自动回退到"全部"；
  // 合法性判断提取为生产纯函数 resolveActiveTab（lib 内已直接测试）。
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
    return sortResults(scoped, sortMode);
  }, [results, effectiveTab, sortMode]);

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
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-cyber-neon-cyan border-t-transparent" />
          <p className="mt-4 text-sm font-mono text-cyber-text-muted">
            正在搜索中...
          </p>
        </div>
      );
    }
    return null;
  }

  return (
    <div className="mt-6">
      {/* Tab Bar + Sort Selector */}
      <div className="flex items-end justify-between gap-2 flex-wrap border-b border-cyber-border-subtle pb-2 mb-4">
        <div className="flex gap-1 flex-wrap">
          {visibleTabs.map((tab) => {
            const count = counts[tab.key] || 0;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`px-3 py-1.5 rounded-t-lg text-xs font-mono transition-all ${
                  effectiveTab === tab.key
                    ? "text-cyber-neon-cyan border-b-2 border-cyber-neon-cyan bg-cyber-neon-cyan/5"
                    : "text-cyber-text-muted hover:text-cyber-text-primary"
                }`}
              >
                {tab.icon && <span className="mr-1">{tab.icon}</span>}
                {tab.label}
                {count > 0 && (
                  <span className="ml-1.5 px-1.5 py-0.5 rounded text-[10px] bg-cyber-bg-tertiary">
                    {count}
                  </span>
                )}
              </button>
            );
          })}
        </div>
        {onSortModeChange && (
          <div className="flex gap-1 mb-1" role="group" aria-label="排序方式">
            {SORT_MODES.map((m) => (
              <button
                key={m.key}
                type="button"
                onClick={() => onSortModeChange(m.key)}
                className={`px-2.5 py-1 rounded-md text-[11px] font-mono border transition-all ${
                  sortMode === m.key
                    ? "border-cyber-neon-cyan/60 bg-cyber-neon-cyan/10 text-cyber-neon-cyan"
                    : "border-cyber-border-subtle bg-cyber-bg-tertiary text-cyber-text-muted hover:text-cyber-text-primary"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Result Cards */}
      <div className="space-y-3">
        {filteredResults.map((result, i) => (
          <ResultCard key={`${result.platform}-${result.content_id}-${i}`} result={result} />
        ))}
      </div>

      {filteredResults.length === 0 && (
        <p className="text-center py-8 text-sm font-mono text-cyber-text-muted">
          该平台暂无结果
        </p>
      )}
    </div>
  );
}
