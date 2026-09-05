import { test } from "node:test";
import assert from "node:assert/strict";
import { addBookmarks, BOOKMARKS_KEY, MAX_BOOKMARKS, readBookmarks, setBookmarkNote, writeBookmarks, type BookmarkStorage } from "../src/lib/bookmarks.js";
import { DEFAULT_FILTERS, exportRows, filterResultGroups, groupKey, highlightSegments, matchesFilters, resultKey, resultLinks, resultsCsv, resultsMarkdown, safeContentUrl } from "../src/lib/resultTools.js";
import type { UnifiedSearchResult } from "../src/types/search.js";

const NOW = "2026-09-06T12:00:00Z";
const nowMs = Date.parse(NOW);
function result(id: string, overrides: Partial<UnifiedSearchResult> = {}): UnifiedSearchResult {
  return { platform: "xhs", content_id: id, content_type: "note", title: `Python 教程 ${id}`,
    author: "作者", url: `https://www.xiaohongshu.com/explore/${id}`, published_at: "2026-09-05T12:00:00Z",
    snippet: "介绍 Python 安装与基础语法", metrics: {}, cover_url: null, rank: 0, ...overrides };
}
function group(): UnifiedSearchResult {
  const note = result("note", { published_at: "2026-07-01T00:00:00Z" });
  const video = result("video", { platform: "bilibili", content_type: "video", url: "https://www.bilibili.com/video/BVtest" });
  return { ...note, grouped_sources: [note, video] };
}
class Storage implements BookmarkStorage {
  value: string | null = null;
  getItem(key: string): string | null { assert.equal(key, BOOKMARKS_KEY); return this.value; }
  setItem(key: string, value: string): void { assert.equal(key, BOOKMARKS_KEY); this.value = value; }
}
const metadata = () => ({ fetchedAt: NOW, savedAt: null, note: "" });

test("时间筛选包含边界，排除范围外、未来和未知日期", () => {
  const filters = { ...DEFAULT_FILTERS, days: 7 as const };
  for (const published_at of ["2026-08-30T12:00:00Z", NOW]) assert.ok(matchesFilters(result("a", { published_at }), filters, nowMs));
  for (const published_at of [null, "invalid", "2026-08-30T11:59:59Z", "2026-09-07T00:00:00Z"]) {
    assert.equal(matchesFilters(result("a", { published_at }), filters, nowMs), false);
  }
  assert.ok(matchesFilters(result("a", { published_at: null }), DEFAULT_FILTERS, nowMs));
  assert.ok(matchesFilters(result("a", { published_at: "2026-08-08T12:00:00Z" }), { ...filters, days: 30 }, nowMs));
});

test("内容类型覆盖视频、图文帖子和文章回答", () => {
  for (const content_type of ["video", "short_video", "zvideo"]) assert.ok(matchesFilters(result("a", { content_type }), { ...DEFAULT_FILTERS, contentType: "video" }, nowMs));
  for (const content_type of ["article", "answer"]) assert.ok(matchesFilters(result("a", { content_type }), { ...DEFAULT_FILTERS, contentType: "article" }, nowMs));
  assert.equal(matchesFilters(result("a"), { ...DEFAULT_FILTERS, contentType: "video" }, nowMs), false);
});

test("关键词按词同时匹配标题、作者、摘要，兼容全角与大小写", () => {
  assert.ok(matchesFilters(result("a"), { ...DEFAULT_FILTERS, query: "ＰＹＴＨＯＮ 作者 安装" }, nowMs));
  assert.equal(matchesFilters(result("a"), { ...DEFAULT_FILTERS, query: "Python 数据库" }, nowMs), false);
});

test("分组筛选必须在同一来源上满足全部条件", () => {
  assert.equal(filterResultGroups([group()], { ...DEFAULT_FILTERS, days: 7, contentType: "note" }, nowMs).length, 0);
  const filtered = filterResultGroups([group()], { ...DEFAULT_FILTERS, days: 7, contentType: "video" }, nowMs);
  assert.equal(filtered.length, 1);
  assert.equal(filtered[0].platform, "bilibili");
  assert.equal(filtered[0].grouped_sources, null);
  assert.equal(filterResultGroups([group()], DEFAULT_FILTERS, nowMs, "xhs")[0].content_id, "note");
});

test("筛选不修改源数据，分组身份不依赖代表排序", () => {
  const original = group();
  const snapshot = JSON.stringify(original);
  filterResultGroups([original], { ...DEFAULT_FILTERS, days: 7 }, nowMs);
  assert.equal(JSON.stringify(original), snapshot);
  assert.equal(groupKey(original), groupKey({ ...original, grouped_sources: [...original.grouped_sources!].reverse() }));
});

test("高亮把正则字符当普通文字处理，文本原样保留", () => {
  const text = "C++ <script> 与 Python";
  const segments = highlightSegments(text, "C++ <script>");
  assert.equal(segments.map((part) => part.text).join(""), text);
  assert.deepEqual(segments.filter((part) => part.matched).map((part) => part.text), ["C++", "<script>"]);
  assert.deepEqual(highlightSegments("plain", ""), [{ text: "plain", matched: false }]);
});

test("收藏保存所有来源，重载后保留时间与备注", () => {
  const storage = new Storage();
  let items = addBookmarks([], [group()], NOW, { xhs: "2026-09-06T11:00:00Z", bilibili: NOW });
  assert.equal(items.length, 2);
  items = setBookmarkNote(items, "bilibili|video", "需要复习");
  writeBookmarks(storage, items);
  const restored = readBookmarks(storage);
  assert.deepEqual(restored, items);
  assert.equal(restored[1].note, "需要复习");
  assert.equal(restored[0].fetchedAt, "2026-09-06T11:00:00Z");
  assert.equal(restored[0].result.grouped_sources, null);
});

test("重复收藏和单平台收藏不会覆盖已有快照与备注", () => {
  const initial = setBookmarkNote(addBookmarks([], [group()], NOW), "xhs|note", "原备注");
  const again = addBookmarks(initial, [result("note", { title: "已变化的标题" })], "2026-09-07T12:00:00Z");
  assert.deepEqual(again, initial);
  assert.throws(() => setBookmarkNote(initial, "xhs|missing", "备注"));
});

test("收藏只存公开字段，移除额外响应字段和嵌套分组", () => {
  const extra = { ...result("a"), cookies: "private", headers: { token: "private" } };
  const storage = new Storage();
  writeBookmarks(storage, addBookmarks([], [extra], NOW));
  assert.ok(!storage.value!.includes("private"));
});

test("损坏数据不被读取流程覆盖，浏览器拒绝存储会抛错", () => {
  const storage = new Storage();
  storage.value = "{broken";
  assert.throws(() => readBookmarks(storage));
  assert.equal(storage.value, "{broken");
  storage.value = '{"version":99,"items":[]}';
  assert.throws(() => readBookmarks(storage));
  const denied: BookmarkStorage = { getItem: () => null, setItem: () => { throw new Error("quota"); } };
  assert.throws(() => writeBookmarks(denied, addBookmarks([], [result("a")], NOW)));
});

test("容量限制不会静默丢弃旧收藏或只保存半个分组", () => {
  const initial = addBookmarks([], Array.from({ length: MAX_BOOKMARKS - 1 }, (_, index) => result(String(index))), NOW);
  assert.throws(() => addBookmarks(initial, [group()], NOW));
  assert.equal(initial.length, MAX_BOOKMARKS - 1);
  assert.throws(() => setBookmarkNote(initial, "xhs|0", "字".repeat(1001)));
});

test("导出展开分组并按平台和内容 ID 去重，只包含给定范围", () => {
  const rows = exportRows([group(), group()], metadata);
  assert.equal(rows.length, 2);
  const selected = filterResultGroups([group()], { ...DEFAULT_FILTERS, contentType: "video" }, nowMs);
  assert.deepEqual(exportRows(selected, metadata).map((row) => resultKey(row.result)), ["bilibili|video"]);
});

test("CSV 支持中文 BOM、引号换行与公式文本防护", () => {
  const csv = resultsCsv([{ ...metadata(), note: '第一行\n第二行,"引号"', result: result("a", { title: " =SUM(1,2)" }) }]);
  assert.ok(csv.startsWith("\uFEFF"));
  assert.ok(csv.includes('"\' =SUM(1,2)"'));
  assert.ok(csv.includes('"第一行\n第二行,""引号"""'));
  assert.ok(csv.includes(NOW));
  assert.ok(csv.includes("https://www.xiaohongshu.com/explore/a"));
});

test("Markdown 保留来源与备注，转义标题中的标记和 HTML", () => {
  const markdown = resultsMarkdown([{ ...metadata(), note: "**记录**", result: result("a", { title: "[标题]<script>" }) }]);
  assert.ok(markdown.includes("\\[标题\\]\\<script\\>"));
  assert.ok(markdown.includes("备注：\\*\\*记录\\*\\*"));
  assert.ok(markdown.includes("[打开原文](<https://www.xiaohongshu.com/explore/a>)"));
});

test("复制与导出拒绝脚本、仿冒域名和带凭据的链接", () => {
  for (const url of ["javascript:alert(1)", "https://bilibili.com.evil.test/video", "https://user:password@zhihu.com/question/1"]) {
    assert.equal(safeContentUrl(url), null);
    assert.equal(resultLinks(exportRows([result("a", { url })], metadata)), "");
    assert.throws(() => addBookmarks([], [result("a", { url })], NOW));
  }
  assert.equal(safeContentUrl("https://zhuanlan.zhihu.com/p/1"), "https://zhuanlan.zhihu.com/p/1");
});

test("收藏→刷新读取→筛选→导出，备注和采集时间保持一致", () => {
  const storage = new Storage();
  const saved = setBookmarkNote(addBookmarks([], [group()], NOW, { bilibili: NOW }), "bilibili|video", "下周学习");
  writeBookmarks(storage, saved);
  const restored = readBookmarks(storage);
  const filtered = filterResultGroups(restored.map((item) => item.result), { ...DEFAULT_FILTERS, contentType: "video" }, nowMs);
  const rows = exportRows(filtered, (source) => {
    const item = restored.find((candidate) => resultKey(candidate.result) === resultKey(source))!;
    return { fetchedAt: item.fetchedAt, savedAt: item.savedAt, note: item.note };
  });
  assert.equal(rows.length, 1);
  assert.ok(resultsCsv(rows).includes("下周学习"));
  assert.ok(resultsMarkdown(rows).includes(NOW));
});
