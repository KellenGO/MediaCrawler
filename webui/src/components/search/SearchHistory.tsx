import { Clock, X, Trash2 } from "lucide-react";
import type { SearchHistoryItem } from "@/lib/searchExperience";
import { PLATFORM_LABELS } from "@/types/search";

interface SearchHistoryProps {
  history: SearchHistoryItem[];
  disabled: boolean; // 搜索/取消/重试进行中
  onItemClick: (item: SearchHistoryItem) => void;
  onRemove: (index: number) => void;
  onClear: () => void;
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const diff = Date.now() - d.getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return "刚刚";
    if (minutes < 60) return `${minutes}分钟前`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}小时前`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}天前`;
    return d.toLocaleDateString("zh-CN");
  } catch {
    return "";
  }
}

export function SearchHistory({ history, disabled, onItemClick, onRemove, onClear }: SearchHistoryProps) {
  if (history.length === 0) return null;

  return (
    <div className="w-full max-w-2xl mx-auto mt-3">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] font-mono text-cyber-text-muted flex items-center gap-1">
          <Clock className="w-3 h-3" />
          最近搜索
        </span>
        <button
          type="button"
          onClick={onClear}
          disabled={disabled}
          className="text-[11px] font-mono text-cyber-text-muted hover:text-cyber-neon-pink transition-colors flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Trash2 className="w-3 h-3" />清空
        </button>
      </div>
      <ul className="flex flex-wrap gap-1.5">
        {history.map((item, index) => (
          <li key={`${item.keyword}-${item.searchedAt}-${index}`} className="flex items-stretch">
            <button
              type="button"
              disabled={disabled}
              onClick={() => onItemClick(item)}
              title={`搜索「${item.keyword}」· ${item.platforms.map((p) => PLATFORM_LABELS[p] || p).join("、")}`}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-cyber-border-subtle bg-cyber-bg-tertiary text-xs font-mono text-cyber-text-muted hover:border-cyber-neon-cyan/50 hover:text-cyber-neon-cyan transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <span className="max-w-[9rem] truncate">{item.keyword}</span>
              <span className="text-[10px] text-cyber-text-muted/70">
                {item.platforms.map((p) => PLATFORM_LABELS[p]?.charAt(0) || p).join("·")}
              </span>
              {formatTime(item.searchedAt) && (
                <span className="text-[10px] text-cyber-text-muted/50">{formatTime(item.searchedAt)}</span>
              )}
            </button>
            <button
              type="button"
              aria-label={`删除历史「${item.keyword}」`}
              onClick={() => onRemove(index)}
              disabled={disabled}
              className="ml-0.5 flex items-center px-1 text-cyber-text-muted/50 hover:text-cyber-neon-pink transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <X className="w-3 h-3" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
