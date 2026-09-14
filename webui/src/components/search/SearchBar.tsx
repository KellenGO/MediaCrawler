import { useCallback, useEffect, useReducer, useRef, FormEvent, Dispatch, SetStateAction } from "react";
import { ArrowRight, Search, Loader2, X } from "lucide-react";
import type { PlatformSlug } from "@/types/search";
import { PLATFORM_LABELS, PLATFORM_COLORS } from "@/types/search";
import type { SearchHistoryItem } from "@/lib/searchExperience";
import { INITIAL_POPOVER_STATE, searchPopoverReducer } from "@/lib/searchPopover";
import type { PlatformLimitMap } from "@/lib/platformLimits";
import { SearchPopover } from "./SearchPopover";
import { PLATFORM_SLUGS } from "@/lib/platformMeta";

const ALL_PLATFORMS = PLATFORM_SLUGS;


interface SearchBarProps {
  home?: boolean;
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
  home = false,
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
      className={`search-area search-panel relative rounded-[22px] border-0 bg-transparent p-0 shadow-none transition-[border-radius] ${
        popoverOpen === "open" ? "rounded-b-none" : ""
      }`}
    >
      {/* 搜索行：输入 + 按钮 */}
      <div className="search-box search-row flex items-stretch gap-2.5">
        <div className="search-leading" aria-hidden={!keyword || isSearching}>
          {keyword && !isSearching ? (
            <button
              type="button"
              onClick={() => onKeywordChange("")}
              aria-label="清空关键词"
            >
              <X />
            </button>
          ) : (
            <Search aria-hidden="true" />
          )}
        </div>
        <div className="search-input-wrap">
          <input
            type="text"
            value={keyword}
            onChange={(e) => onKeywordChange(e.target.value)}
            placeholder={home ? "搜点什么？" : "搜索话题、人物或产品"}
            maxLength={200}
            disabled={isSearching}
            // Round 14.1：只有输入框聚焦打开浮层；关闭由 document pointerdown
            // 外部点击 / Escape / 提交搜索驱动，不再依赖 blur。
            onFocus={() => dispatchPopover({ type: "focus_within" })}
            className="w-full h-[58px] rounded-full border-0 bg-transparent text-[16px] text-cyber-text-primary placeholder:text-cyber-text-muted focus:outline-none disabled:opacity-50"
          />

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
            className="search-cancel h-[44px] min-w-[104px] self-center flex items-center justify-center gap-2 rounded-full border border-warn/40 bg-warn-soft text-warn font-semibold text-[13px] hover:bg-warn-soft/80 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isCancelling ? <Loader2 className="w-4 h-4 animate-spin" /> : <X className="w-4 h-4" />}
            取消
          </button>
        ) : (
          <button
            type="submit"
            disabled={!keyword.trim()}
            className="search-submit h-[44px] w-[44px] self-center flex items-center justify-center rounded-full bg-brand text-white hover:bg-brand-strong hover:-translate-y-px transition-all disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:translate-y-0"
          >
            <ArrowRight className="w-[17px] h-[17px]" />
            <span className="sr-only">开始搜索</span>
          </button>
        )}
      </div>

      {/* 平台选择：浅色胶囊 */}
      <div className="scope search-scope">
        <span className="scope-label">搜索范围</span>
        {ALL_PLATFORMS.map((p) => {
          const isSelected = selectedPlatforms.has(p);
          const color = PLATFORM_COLORS[p];
          return (
            <button
              key={p}
              type="button"
              disabled={isSearching}
              onClick={() => togglePlatform(p)}
              className="platform-choice"
              aria-pressed={isSelected}
            >
              <i
                className="pd"
                style={{ backgroundColor: color, opacity: isSelected ? 1 : 0.45 }}
              />
              {PLATFORM_LABELS[p]}
              <span className="check" aria-hidden="true">{isSelected ? "✓" : ""}</span>
            </button>
          );
        })}
        <span className="sr-only">每个平台本轮最多 {Math.max(...Object.values(limits))} 条</span>
      </div>
    </form>
  );
}
