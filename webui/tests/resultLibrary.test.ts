import { test } from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_FILTERS, exportRows, filterResultGroups, groupKey, highlightSegments, matchesFilters, resultKey, resultsCsv, resultsMarkdown } from "../src/lib/resultTools.js";
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

