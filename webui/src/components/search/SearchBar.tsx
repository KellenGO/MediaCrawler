import { useCallback, useEffect, useReducer, useRef, FormEvent, Dispatch, SetStateAction } from "react";
import { Search, Loader2, X } from "lucide-react";
import type { PlatformSlug } from "@/types/search";
import { PLATFORM_LABELS, PLATFORM_COLORS } from "@/types/search";
import type { SearchHistoryItem } from "@/lib/searchExperience";
import { INITIAL_POPOVER_STATE, searchPopoverReducer } from "@/lib/searchPopover";
import type { PlatformLimitMap } from "@/lib/platformLimits";
import { SearchPopover } from "./SearchPopover";

const ALL_PLATFORMS: PlatformSlug[] = ["xhs", "douyin", "bilibili", "zhihu"];

interface SearchBarProps {
  keyword: string;
  onKeywordChange: Dispatch<SetStateAction<string>>;
  selectedPlatforms: Set<PlatformSlug>;
  onPlatformsChange: (platforms: PlatformSlug[]) => void;
  onSearch: (keyword: string, platforms: PlatformSlug[]) => void;
  isSearching: boolean;
  onCancel?: () => void;
  isCancelling?: boolean;
  onReset: () => void;
  // 下拉浮层（Round 14）：最近搜索 + 推荐搜索
  history: SearchHistoryItem[];
  onHistoryClick: (item: SearchHistoryItem) => void;
  onHistoryRemove: (index: number) => void;
  onHistoryClear: () => void;
  // Round 15: 每个平台独立搜索数量（仅展示）。
  limits: PlatformLimitMap;
}

export function SearchBar({
  keyword,
  onKeywordChange,
  selectedPlatforms,
  onPlatformsChange,
  onSearch,
  isSearching,
  onCancel,
  isCancelling,
  onReset,
  history,
  onHistoryClick,
  onHistoryRemove,
  onHistoryClear,
  limits,
}: SearchBarProps) {
  // 浮层开/关由生产 reducer 驱动（lib/searchPopover，node:test 已覆盖规则）。
  // 注意：reducer 状态是字符串 "open"/"closed"，两者都 truthy，
  // 因此 JSX 必须用 === "open" 判断，不能用 {popoverOpen && ...}。
  const [popoverOpen, dispatchPopover] = useReducer(searchPopoverReducer, INITIAL_POPOVER_STATE);

  // 整个搜索面板（form）的 ref：判断点击目标是否位于面板内部。
  const searchPanelRef = useRef<HTMLFormElement>(null);

  // Round 14.1：浮层打开时监听 document 的 pointerdown 与 Escape。
  // - pointerdown 且目标位于整个搜索 form 之外 → outside_pointer 关闭；
  // - 目标在 form 内部（输入框/清空按钮/浮层内按钮/平台选择/面板空白）→ 不关闭，
  //   因此内部按钮的 click 事件照常触发（不 preventDefault/stopPropagation）。
  // - 只在 popoverOpen === "open" 时注册；cleanup 移除同一个 listener，
  //   多次打开/关闭不会残留或重复注册。
  useEffect(() => {
    if (popoverOpen !== "open") return;
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (target && searchPanelRef.current && searchPanelRef.current.contains(target)) {
        return; // 点击面板内部：保持打开
      }
      dispatchPopover({ type: "outside_pointer" });
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        dispatchPopover({ type: "escape" });
      }
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [popoverOpen]);

  const togglePlatform = useCallback(
    (p: PlatformSlug) => {
      const next = new Set(selectedPlatforms);
      if (next.has(p)) {
        if (next.size > 1) next.delete(p); // 至少保留一个平台
      } else {
        next.add(p);
      }
      onPlatformsChange(Array.from(next) as PlatformSlug[]);
    },
    [selectedPlatforms, onPlatformsChange]
  );

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      const trimmed = keyword.trim();
      if (!trimmed) return;
      dispatchPopover({ type: "search_started" }); // 开始搜索后关闭浮层
      onSearch(trimmed, Array.from(selectedPlatforms) as PlatformSlug[]);
    },
    [keyword, selectedPlatforms, onSearch]
  );

  // reset：只清空关键词与任务；平台选择与偏好保留（不恢复四平台全选）。
  const handleReset = useCallback(() => {
    onKeywordChange("");
    onReset();
  }, [onKeywordChange, onReset]);

  // 历史项点击：立即回放关键词与平台组合并只发起一次搜索（hook 双 guard 保证）。
  const handleHistoryItemClick = useCallback(
    (item: SearchHistoryItem) => {
      dispatchPopover({ type: "picked" });
      onHistoryClick(item);
    },
    [onHistoryClick]
  );

  // 推荐词：填入关键词并搜索。
  const handleRecommend = useCallback(
    (word: string) => {
      dispatchPopover({ type: "picked" });
      onKeywordChange(word);
      onSearch(word, Array.from(selectedPlatforms) as PlatformSlug[]);
    },
    [onKeywordChange, onSearch, selectedPlatforms]
  );

  return (
    <form
      ref={searchPanelRef}
      onSubmit={handleSubmit}
      className={`relative rounded-[22px] border border-cyber-border-subtle bg-cyber-bg-secondary p-2.5 shadow-[0_24px_70px_rgba(50,105,145,0.10)] transition-[border-radius] ${
        popoverOpen === "open" ? "rounded-b-none" : ""
      }`}
    >
      {/* 搜索行：输入 + 按钮 */}
      <div className="flex items-stretch gap-2.5">
        <div className="relative flex-1">
          <Search className="absolute left-5 top-1/2 -translate-y-1/2 w-[21px] h-[21px] text-cyber-text-muted pointer-events-none" />
          <input
            type="text"
            value={keyword}
            onChange={(e) => onKeywordChange(e.target.value)}
            placeholder="搜索一个话题、人物或产品…"
            maxLength={200}
            disabled={isSearching}
            // Round 14.1：只有输入框聚焦打开浮层；关闭由 document pointerdown
            // 外部点击 / Escape / 提交搜索驱动，不再依赖 blur。
            onFocus={() => dispatchPopover({ type: "focus_within" })}
            className="w-full h-[64px] pl-14 pr-11 rounded-[15px] border-0 bg-transparent text-[17px] text-cyber-text-primary placeholder:text-cyber-text-muted focus:outline-none disabled:opacity-50"
          />
          {keyword && !isSearching && (
            <button
              type="button"
              onClick={() => onKeywordChange("")}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-cyber-text-muted hover:text-cyber-text-primary"
              aria-label="清空关键词"
            >
              <X className="w-[18px] h-[18px]" />
            </button>
          )}

          {/* 聚焦浮层：最近搜索 + 推荐搜索（必须 === "open"，"closed" 也是 truthy 字符串） */}
          {popoverOpen === "open" && (
            <SearchPopover
              history={history}
              disabled={isSearching}
              onItemClick={handleHistoryItemClick}
              onRemove={onHistoryRemove}
              onClear={onHistoryClear}
              onRecommend={handleRecommend}
            />
          )}
        </div>

        {isSearching ? (
          <button
            type="button"
            onClick={() => (onCancel ? onCancel() : handleReset())}
            disabled={isCancelling}
            className="h-[56px] min-w-[120px] flex items-center justify-center gap-2 rounded-[15px] border border-warn/40 bg-warn-soft text-warn font-semibold text-[14px] hover:bg-warn-soft/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isCancelling ? <Loader2 className="w-4 h-4 animate-spin" /> : <X className="w-4 h-4" />}
            取消
          </button>
        ) : (
          <button
            type="submit"
            disabled={!keyword.trim()}
            className="h-[56px] min-w-[136px] flex items-center justify-center gap-2 rounded-[15px] bg-brand text-white font-bold text-[14.5px] shadow-[0_8px_22px_rgba(76,164,220,0.25)] hover:bg-brand-strong hover:-translate-y-px transition-all disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:translate-y-0"
          >
            <Search className="w-[17px] h-[17px]" />
            开始搜索
          </button>
        )}
      </div>

      {/* 平台选择：浅色胶囊 */}
      <div className="mt-2 pt-2.5 border-t border-cyber-border-subtle flex items-center gap-1.5 flex-wrap px-1">
        <span className="text-[12px] text-cyber-text-muted mr-1">搜索范围</span>
        {ALL_PLATFORMS.map((p) => {
          const isSelected = selectedPlatforms.has(p);
          const color = PLATFORM_COLORS[p];
          return (
            <button
              key={p}
              type="button"
              disabled={isSearching}
              onClick={() => togglePlatform(p)}
              className={`flex items-center gap-2 rounded-full px-3.5 py-2 text-[12.5px] transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                isSelected
                  ? "bg-brand-soft text-brand-ink border border-brand/25"
                  : "border border-transparent text-cyber-text-muted hover:text-cyber-text-primary"
              }`}
            >
              <i
                className="w-2 h-2 rounded-[3px] flex-shrink-0"
                style={{ backgroundColor: color, opacity: isSelected ? 1 : 0.45 }}
              />
              {PLATFORM_LABELS[p]}
              <span className="ml-0.5 text-[10px] leading-none px-1.5 py-1 rounded-full bg-cyber-bg-tertiary text-cyber-text-muted">
                {limits[p]}
              </span>
            </button>
          );
        })}
        <span className="ml-auto hidden sm:inline text-[12px] text-cyber-text-muted pr-1.5">按平台设置 · 单个平台最多 20 条</span>
      </div>
    </form>
  );
}
