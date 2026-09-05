import { useEffect, useId, useState } from "react";
import { Bookmark as BookmarkIcon, Check, Copy, Download } from "lucide-react";
import { toast } from "sonner";
import type { BookmarkLibrary } from "@/hooks/useBookmarks";
import type { PlatformSlug, UnifiedSearchResult } from "@/types/search";
import type { Bookmark } from "@/lib/bookmarks";
import { MAX_NOTE_LENGTH } from "@/lib/bookmarks";
import { resultKey, resultLinks, resultSources, resultsCsv, resultsMarkdown, type ExportRow } from "@/lib/resultTools";

export const TOOL_BUTTON = "inline-flex items-center gap-1.5 rounded-lg border border-cyber-border-subtle px-2.5 py-1.5 text-xs text-cyber-text-secondary hover:text-brand-strong hover:border-brand/50 disabled:opacity-40 disabled:cursor-not-allowed";

export function ExportActions({ rows, keyword }: { rows: ExportRow[]; keyword: string }) {
  const download = (format: "csv" | "md") => {
    try {
      const contents = format === "csv" ? resultsCsv(rows) : resultsMarkdown(rows);
      const blob = new Blob([contents], { type: format === "csv" ? "text/csv;charset=utf-8" : "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      const name = keyword.replace(/[^\p{L}\p{N}._-]+/gu, "_").slice(0, 48) || "搜索结果";
      anchor.download = `${name}-${new Date().toISOString().replace(/[:.]/g, "-")}.${format}`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      toast.error("导出失败，请重试。");
    }
  };
  const copy = async () => {
    try {
      const links = resultLinks(rows);
      if (!links) { toast.error("当前结果没有可复制的原文链接。"); return; }
      await navigator.clipboard.writeText(links);
      toast.success("原文链接已复制");
    } catch { toast.error("复制失败，请允许浏览器访问剪贴板，或使用导出功能。"); }
  };
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" className={TOOL_BUTTON} disabled={!rows.length} onClick={() => download("csv")}><Download className="w-3.5 h-3.5" />导出 CSV</button>
      <button type="button" className={TOOL_BUTTON} disabled={!rows.length} onClick={() => download("md")}>导出 Markdown</button>
      <button type="button" className={TOOL_BUTTON} disabled={!rows.length} onClick={() => void copy()}><Copy className="w-3.5 h-3.5" />复制链接</button>
    </div>
  );
}

export function BookmarkButton({ result, library, fetchedAt }: {
  result: UnifiedSearchResult; library: BookmarkLibrary;
  fetchedAt: Partial<Record<PlatformSlug, string | null>>;
}) {
  const keys = new Set(library.items.map((item) => resultKey(item.result)));
  const sources = resultSources(result);
  const saved = sources.every((source) => keys.has(resultKey(source)));
  const label = saved ? "取消收藏" : sources.length > 1 ? "收藏全部来源" : "收藏";
  return (
    <button type="button" aria-label={`${label} ${result.title}`} aria-pressed={saved}
      className={TOOL_BUTTON} onClick={() => library.toggle(result, fetchedAt)}>
      {saved ? <Check className="w-3.5 h-3.5 text-brand-strong" /> : <BookmarkIcon className="w-3.5 h-3.5" />}
      {saved ? "已收藏" : label}
    </button>
  );
}

export function BookmarkNote({ bookmark, onSave }: { bookmark: Bookmark; onSave: (key: string, note: string) => boolean }) {
  const [draft, setDraft] = useState(bookmark.note);
  const id = useId();
  useEffect(() => setDraft(bookmark.note), [bookmark.note]);
  return (
    <div className="mt-2 rounded-xl border border-cyber-border-subtle bg-cyber-bg-secondary p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-cyber-text-muted mb-2">
        <label htmlFor={id}>备注</label>
        <span>收藏于 {new Date(bookmark.savedAt).toLocaleString("zh-CN")}</span>
      </div>
      <textarea id={id} aria-label={`备注 ${bookmark.result.title}`} value={draft} maxLength={MAX_NOTE_LENGTH}
        rows={2} onChange={(event) => setDraft(event.target.value)}
        className="w-full rounded-lg border border-cyber-border-subtle bg-cyber-bg-primary p-2 text-sm text-cyber-text-primary focus:outline-none focus:ring-2 focus:ring-brand/40"
        placeholder="记录这条内容对你有什么用…" />
      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="text-xs text-cyber-text-muted">{draft.length}/{MAX_NOTE_LENGTH}{draft !== bookmark.note ? " · 尚未保存" : ""}</span>
        <button type="button" className={TOOL_BUTTON} disabled={draft === bookmark.note} onClick={() => {
          if (onSave(resultKey(bookmark.result), draft)) toast.success("备注已保存");
        }}>保存备注</button>
      </div>
    </div>
  );
}
