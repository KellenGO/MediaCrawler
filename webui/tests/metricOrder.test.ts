/**
 * 互动数据展示顺序测试 —— 直接 import 生产模块（src/lib/resultTools.ts），
 * 顺序要求：播放 → 点赞 → 投币 → 评论 → 收藏（B站投币紧跟点赞）。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { METRIC_ORDER, orderedMetrics } from "../src/lib/resultTools.js";

const keysOf = (metrics: Record<string, number>, limit?: number): string[] =>
  orderedMetrics(metrics, limit).map((entry) => entry.key);

test("METRIC_ORDER: 核心五项顺序固定，投币紧跟点赞", () => {
  assert.deepEqual(
    METRIC_ORDER.slice(0, 5).map(([key]) => key),
    ["view_count", "like_count", "coin_count", "comment_count", "collect_count"],
  );
});

test("orderedMetrics: 六项齐全时按既定顺序陈列", () => {
  assert.deepEqual(
    keysOf({
      share_count: 1, collect_count: 3, comment_count: 4,
      coin_count: 5, like_count: 6, view_count: 7,
    }),
    ["view_count", "like_count", "coin_count", "comment_count", "collect_count",
      "share_count"],
  );
});

test("orderedMetrics: 弹幕数据仍被采集但不参与展示", () => {
  assert.deepEqual(
    keysOf({
      view_count: 350000, like_count: 22000, coin_count: 4500,
      comment_count: 650, collect_count: 12000, danmaku_count: 2800,
    }),
    ["view_count", "like_count", "coin_count", "comment_count", "collect_count"],
  );
  assert.ok(!METRIC_ORDER.some(([key]) => key === "danmaku_count"));
});

test("orderedMetrics: B站结果里投币排在点赞之后、评论之前", () => {
  const bilibili = {
    view_count: 350000, like_count: 22000, coin_count: 4500, comment_count: 650,
  };
  assert.deepEqual(keysOf(bilibili), [
    "view_count", "like_count", "coin_count", "comment_count",
  ]);
});

test("orderedMetrics: 平台缺项时保持相对顺序，不占位", () => {
  // 小红书搜索：没有播放量，只有点赞/评论/收藏/分享。
  assert.deepEqual(
    keysOf({ like_count: 47039, collect_count: 34361, comment_count: 391, share_count: 1667 }),
    ["like_count", "comment_count", "collect_count", "share_count"],
  );
  // 知乎：没有收藏数。
  assert.deepEqual(
    keysOf({ like_count: 655, comment_count: 18, view_count: 20105854 }),
    ["view_count", "like_count", "comment_count"],
  );
});

test("orderedMetrics: 真实零值显示，缺失和非法值不占位", () => {
  assert.deepEqual(keysOf({ like_count: 0, view_count: 0 }), ["view_count", "like_count"]);
  assert.deepEqual(keysOf({ like_count: NaN, view_count: -1, comment_count: Infinity }), []);
  assert.deepEqual(keysOf({}), []);
  assert.deepEqual(orderedMetrics(null), []);
  assert.deepEqual(orderedMetrics(undefined), []);
});

test("orderedMetrics: limit 截断发生在排序之后", () => {
  const metrics = {
    view_count: 7, like_count: 6, coin_count: 5, comment_count: 4,
    collect_count: 3, danmaku_count: 2, share_count: 1,
  };
  assert.deepEqual(keysOf(metrics, 2), ["view_count", "like_count"]);
  assert.deepEqual(keysOf(metrics, 4), ["view_count", "like_count", "coin_count", "comment_count"]);
});

test("orderedMetrics: 中文标签与字段一一对应", () => {
  const labels = new Map(METRIC_ORDER.map(([key, label]) => [key, label]));
  assert.equal(labels.get("view_count"), "播放");
  assert.equal(labels.get("like_count"), "点赞");
  assert.equal(labels.get("coin_count"), "投币");
  assert.equal(labels.get("comment_count"), "评论");
  assert.equal(labels.get("collect_count"), "收藏");
});
