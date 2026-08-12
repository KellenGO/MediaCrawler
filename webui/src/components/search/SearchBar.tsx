import { useState, useCallback, FormEvent } from "react";
import { Search, Loader2, X } from "lucide-react"; // eslint-disable-line
import type { PlatformSlug } from "@/types/search";
import { PLATFORM_LABELS, PLATFORM_ICONS } from "@/types/search";

interface SearchBarProps {
  onSearch: (keyword: string, platforms: PlatformSlug[]) => void;
  isSearching: boolean;
  onCancel?: () => void;
  isCancelling?: boolean;
  onReset: () => void;
}

const ALL_PLATFORMS: PlatformSlug[] = ["xhs", "douyin", "bilibili", "zhihu"];

export function SearchBar({ onSearch, isSearching, onCancel, isCancelling, onReset }: SearchBarProps) {
  const [keyword, setKeyword] = useState("");
  const [selectedPlatforms, setSelectedPlatforms] = useState<Set<PlatformSlug>>(
    new Set(ALL_PLATFORMS)
  );

  const togglePlatform = useCallback((p: PlatformSlug) => {
    setSelectedPlatforms((prev) => {
      const next = new Set(prev);
      if (next.has(p)) {
        if (next.size > 1) next.delete(p);
      } else {
        next.add(p);
      }
      return next;
    });
  }, []);

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      const trimmed = keyword.trim();
      if (!trimmed) return;
      const platforms = Array.from(selectedPlatforms) as PlatformSlug[];
      onSearch(trimmed, platforms);
    },
    [keyword, selectedPlatforms, onSearch]
  );

  const handleReset = useCallback(() => {
    setKeyword("");
    setSelectedPlatforms(new Set(ALL_PLATFORMS));
    onReset();
  }, [onReset]);

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-2xl mx-auto">
      {/* Search Input */}
      <div className="relative flex items-center">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-cyber-text-muted" />
          <input
            type="text"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="输入关键词搜索..."
            maxLength={200}
            disabled={isSearching}
            className="w-full h-12 pl-12 pr-4 rounded-xl border border-cyber-border-subtle bg-cyber-bg-secondary text-cyber-text-primary font-mono text-sm placeholder:text-cyber-text-muted focus:outline-none focus:border-cyber-neon-cyan focus:shadow-glow-cyan-sm transition-all disabled:opacity-50"
            autoFocus
          />
          {keyword && (
            <button
              type="button"
              onClick={() => setKeyword("")}
              className="absolute right-14 top-1/2 -translate-y-1/2 text-cyber-text-muted hover:text-cyber-text-primary"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
        {isSearching ? (
          <button
            type="button"
            onClick={() => onCancel ? onCancel() : handleReset()}
            disabled={isCancelling}
            className="ml-3 h-12 px-4 rounded-xl border border-cyber-neon-orange/50 bg-cyber-neon-orange/10 text-cyber-neon-orange font-mono text-sm hover:bg-cyber-neon-orange/20 transition-all flex items-center gap-2 disabled:opacity-50"
          >
            {isCancelling ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <X className="w-4 h-4" />
            )}
            取消
          </button>
        ) : (
          <button
            type="submit"
            disabled={!keyword.trim()}
            className="ml-3 h-12 px-6 rounded-xl bg-cyber-neon-cyan text-black font-mono text-sm font-bold hover:shadow-glow-cyan-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isSearching ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Search className="w-4 h-4" />
            )}
            搜索
          </button>
        )}
      </div>

      {/* Platform Toggles */}
      <div className="flex flex-wrap justify-center gap-2 mt-4">
        {ALL_PLATFORMS.map((p) => {
          const isSelected = selectedPlatforms.has(p);
          return (
            <button
              key={p}
              type="button"
              disabled={isSearching}
              onClick={() => togglePlatform(p)}
              className={`px-3 py-1.5 rounded-lg text-xs font-mono border transition-all ${
                isSelected
                  ? "border-cyber-neon-cyan bg-cyber-neon-cyan/10 text-cyber-neon-cyan"
                  : "border-cyber-border-subtle bg-cyber-bg-tertiary text-cyber-text-muted hover:border-cyber-text-muted"
              } disabled:opacity-50`}
            >
              {PLATFORM_ICONS[p]} {PLATFORM_LABELS[p]}
            </button>
          );
        })}
      </div>
    </form>
  );
}
