import type { PlatformSlug, UnifiedSearchResult } from "../types/search.js";
import { resultKey, resultSources, safeContentUrl } from "./resultTools.js";

export const BOOKMARKS_KEY = "aggregate_search_bookmarks_v1";
export const MAX_BOOKMARKS = 500;
export const MAX_NOTE_LENGTH = 1000;
export const MAX_BACKUP_BYTES = 10 * 1024 * 1024;

export interface Bookmark {
  result: UnifiedSearchResult;
  savedAt: string;
  fetchedAt: string | null;
  note: string;
}
export interface BookmarkStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const optionalText = (value: unknown): string | null => typeof value === "string" ? value : null;
const validTime = (value: unknown): value is string => typeof value === "string" && Number.isFinite(Date.parse(value));

/** Store public DTO fields only; never persist arbitrary extra data from a response. */
function publicResult(value: unknown): UnifiedSearchResult {
  if (!isRecord(value) || !["xhs", "douyin", "bilibili", "zhihu"].includes(String(value.platform))
      || typeof value.content_id !== "string" || !value.content_id || typeof value.title !== "string"
      || typeof value.url !== "string" || !safeContentUrl(value.url)) throw new Error("收藏内容格式或原文链接无效");
  const metrics: Record<string, number> = {};
  if (isRecord(value.metrics)) {
    for (const key of ["like_count", "view_count", "collect_count", "comment_count", "share_count", "coin_count", "danmaku_count"]) {
      const count = value.metrics[key];
      if (typeof count === "number" && Number.isFinite(count) && count >= 0) metrics[key] = count;
    }
  }
  const collectionNames = Array.isArray(value.collection_names)
    ? value.collection_names.filter((name): name is string => typeof name === "string" && name.length <= 200).slice(0, 20)
    : [];
  return {
    platform: value.platform as PlatformSlug, content_id: value.content_id, title: value.title,
    url: safeContentUrl(value.url)!, content_type: typeof value.content_type === "string" ? value.content_type : "note",
    author: optionalText(value.author), snippet: optionalText(value.snippet),
    published_at: validTime(value.published_at) ? value.published_at : null,
    cover_url: optionalText(value.cover_url), metrics,
    rank: typeof value.rank === "number" && Number.isFinite(value.rank) ? value.rank : 0,
    grouped_sources: null,
    collection_names: collectionNames,
  };
}

export function readBookmarks(storage: BookmarkStorage): Bookmark[] {
  const raw = storage.getItem(BOOKMARKS_KEY);
  if (raw === null) return [];
  return parseBookmarkBackup(raw);
}

export function parseBookmarkBackup(raw: string): Bookmark[] {
  if (new TextEncoder().encode(raw).length > MAX_BACKUP_BYTES) throw new Error("收藏备份不能超过 10 MB");
  const data: unknown = JSON.parse(raw);
  if (!isRecord(data) || data.version !== 1 || !Array.isArray(data.items) || data.items.length > MAX_BOOKMARKS) {
    throw new Error("收藏数据无法读取，未覆盖原数据");
  }
  const seen = new Set<string>();
  return data.items.map((item: unknown) => {
    if (!isRecord(item) || !validTime(item.savedAt) || typeof item.note !== "string"
        || item.note.length > MAX_NOTE_LENGTH || (item.fetchedAt !== null && !validTime(item.fetchedAt))) {
      throw new Error("收藏数据无法读取，未覆盖原数据");
    }
    const result = publicResult(item.result);
    if (seen.has(resultKey(result))) throw new Error("收藏数据包含重复条目，未覆盖原数据");
    seen.add(resultKey(result));
    return { result, savedAt: item.savedAt, fetchedAt: item.fetchedAt as string | null, note: item.note };
  });
}

export function bookmarkBackup(items: Bookmark[]): string {
  const raw = JSON.stringify({ version: 1, items });
  return JSON.stringify({ version: 1, items: parseBookmarkBackup(raw) });
}

export function mergeBookmarkBackup(items: Bookmark[], incoming: Bookmark[]): Bookmark[] {
  const keys = new Set(items.map((item) => resultKey(item.result)));
  const additions = incoming.filter((item) => !keys.has(resultKey(item.result)));
  if (items.length + additions.length > MAX_BOOKMARKS) throw new Error(`导入后超过 ${MAX_BOOKMARKS} 条，未修改现有收藏`);
  return [...additions, ...items];
}

export function writeBookmarks(storage: BookmarkStorage, items: Bookmark[]): void {
  if (items.length > MAX_BOOKMARKS) throw new Error(`本地收藏最多 ${MAX_BOOKMARKS} 条，请先导出并整理`);
  storage.setItem(BOOKMARKS_KEY, JSON.stringify({ version: 1, items }));
}

export function addBookmarks(
  items: readonly Bookmark[], results: readonly UnifiedSearchResult[], nowIso: string,
  fetchedAt: Partial<Record<PlatformSlug, string | null>> = {}
): Bookmark[] {
  const byKey = new Map(items.map((item) => [resultKey(item.result), item]));
  const additions: Bookmark[] = [];
  for (const source of results.flatMap(resultSources)) {
    const key = resultKey(source);
    if (byKey.has(key)) continue; // Preserve the user's saved snapshot and note.
    const item = {
      result: publicResult(source), savedAt: nowIso, note: "",
      fetchedAt: validTime(fetchedAt[source.platform]) ? fetchedAt[source.platform]! : null,
    };
    byKey.set(key, item);
    additions.push(item);
  }
  if (byKey.size > MAX_BOOKMARKS) throw new Error(`本地收藏最多 ${MAX_BOOKMARKS} 条，请先导出并整理`);
  return [...additions, ...items];
}

export function setBookmarkNote(items: readonly Bookmark[], key: string, note: string): Bookmark[] {
  if (note.length > MAX_NOTE_LENGTH) throw new Error(`备注最多 ${MAX_NOTE_LENGTH} 字`);
  if (!items.some((item) => resultKey(item.result) === key)) throw new Error("这条收藏已在其他页面移除");
  return items.map((item) => resultKey(item.result) === key ? { ...item, note } : item);
}
