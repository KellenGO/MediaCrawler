import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import type { PlatformSlug, UnifiedSearchResult } from "@/types/search";
import { addBookmarks, BOOKMARKS_KEY, mergeBookmarkBackup, parseBookmarkBackup, readBookmarks, setBookmarkNote, writeBookmarks, type Bookmark } from "@/lib/bookmarks";
import { resultKey, resultSources } from "@/lib/resultTools";

function load(): { items: Bookmark[]; error: string | null } {
  try { return { items: readBookmarks(window.localStorage), error: null }; }
  catch { return { items: [], error: "本地收藏无法读取，原数据未被修改。请检查浏览器存储权限。" }; }
}

export function useBookmarks() {
  const [state, setState] = useState(load);
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key === BOOKMARKS_KEY || event.key === null) setState(load());
    };
    window.addEventListener("storage", sync);
    return () => window.removeEventListener("storage", sync);
  }, []);

  const update = useCallback((change: (items: Bookmark[]) => Bookmark[]): boolean => {
    try {
      // Read before each edit so sequential edits from another tab are preserved.
      const storage = window.localStorage;
      const next = change(readBookmarks(storage));
      writeBookmarks(storage, next);
      setState({ items: next, error: null });
      return true;
    } catch (error) {
      const message = error instanceof Error && error.name === "Error" ? error.message
        : "收藏未保存：浏览器存储不可用或空间不足。请先导出已有收藏。";
      toast.error(message);
      return false;
    }
  }, []);

  const toggle = useCallback((result: UnifiedSearchResult, fetchedAt: Partial<Record<PlatformSlug, string | null>> = {}) => {
    update((items) => {
      const keys = new Set(resultSources(result).map(resultKey));
      const existing = new Set(items.map((item) => resultKey(item.result)));
      return [...keys].every((key) => existing.has(key))
        ? items.filter((item) => !keys.has(resultKey(item.result)))
        : addBookmarks(items, [result], new Date().toISOString(), fetchedAt);
    });
  }, [update]);

  const saveNote = useCallback((key: string, note: string) => update((items) => setBookmarkNote(items, key, note)), [update]);
  const importBackup = useCallback((raw: string) => {
    let added = 0;
    const saved = update((items) => {
      const next = mergeBookmarkBackup(items, parseBookmarkBackup(raw));
      added = next.length - items.length;
      return next;
    });
    if (saved) toast.success(`已导入 ${added} 条收藏，重复内容保留现有快照和备注`);
    return saved;
  }, [update]);
  return { ...state, toggle, saveNote, importBackup };
}

export type BookmarkLibrary = ReturnType<typeof useBookmarks>;
