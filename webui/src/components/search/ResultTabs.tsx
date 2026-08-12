import { useState, useMemo } from "react";
import type { PlatformSlug, UnifiedSearchResult } from "@/types/search";
import { ResultCard } from "./ResultCard";

interface ResultTabsProps {
  results: UnifiedSearchResult[];
  overall: string;
  platforms: PlatformSlug[];
}

type TabKey = "all" | PlatformSlug;
const ALL_TABS: { key: TabKey; label: string; icon?: string }[] = [
  { key: "all", label: "全部" },
  { key: "xhs", label: "小红书", icon: "📕" },
  { key: "douyin", label: "抖音", icon: "🎵" },
  { key: "bilibili", label: "B站", icon: "📺" },
  { key: "zhihu", label: "知乎", icon: "💡" },
];

export function ResultTabs({ results, overall, platforms }: ResultTabsProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("all");

  // Only show tabs for the platforms that were actually searched
  const visibleTabs = useMemo(() => {
    const allowed = new Set(platforms);
    return ALL_TABS.filter(t => t.key === "all" || allowed.has(t.key));
  }, [platforms]);

  const filteredResults = useMemo(() => {
    if (activeTab === "all") return results;
    return results.filter((r) => r.platform === activeTab);
  }, [results, activeTab]);

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
      {/* Tab Bar */}
      <div className="flex gap-1 border-b border-cyber-border-subtle pb-2 mb-4">
        {visibleTabs.map((tab) => {
          const count = counts[tab.key] || 0;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-3 py-1.5 rounded-t-lg text-xs font-mono transition-all ${
                activeTab === tab.key
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
