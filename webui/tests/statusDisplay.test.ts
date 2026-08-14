/**
 * Phase 1 状态卡片耗时展示纯逻辑测试 —— 直接 import 生产模块
 * （webui/src/lib/statusDisplay.ts），不复制生产逻辑。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { formatSeconds, statusLine, timingLine } from "../src/lib/statusDisplay.js";
import type { PlatformStatusInfo } from "../src/types/search.js";

function info(overrides: Partial<PlatformStatusInfo> = {}): PlatformStatusInfo {
  return {
    status: "succeeded",
    result_count: 0,
    error_summary: null,
    timings: null,
    ...overrides,
  };
}

test("formatSeconds: 无数据返回 null", () => {
  assert.equal(formatSeconds(null), null);
  assert.equal(formatSeconds(undefined), null);
});

test("formatSeconds: 毫秒转秒一位小数", () => {
  assert.equal(formatSeconds(1300), "1.3s");
  assert.equal(formatSeconds(4800), "4.8s");
  assert.equal(formatSeconds(0), "0.0s");
});

test("timingLine: 无 timings 返回 null（不占位）", () => {
  assert.equal(timingLine(info({ timings: null })), null);
});

test("timingLine: 首条+完成", () => {
  assert.equal(
    timingLine(info({ timings: { spawn_ms: 120, first_result_ms: 1300, total_ms: 4800 } })),
    "首条 1.3s · 完成 4.8s"
  );
});

test("timingLine: 只有完成", () => {
  assert.equal(
    timingLine(info({ timings: { spawn_ms: null, first_result_ms: null, total_ms: 2000 } })),
    "完成 2.0s"
  );
});

test("timingLine: 只有首条", () => {
  assert.equal(
    timingLine(info({ timings: { spawn_ms: null, first_result_ms: 900, total_ms: null } })),
    "首条 0.9s"
  );
});

test("statusLine: 终态追加耗时", () => {
  const line = statusLine("succeeded", info({
    result_count: 4,
    timings: { spawn_ms: 100, first_result_ms: 1300, total_ms: 4800 },
  }));
  assert.equal(line, "4 条结果 · 首条 1.3s · 完成 4.8s");
});

test("statusLine: 终态无耗时保持原文案", () => {
  assert.equal(statusLine("succeeded", info({ result_count: 4 })), "4 条结果");
  assert.equal(statusLine("empty", info()), "无结果");
  assert.equal(statusLine("cancelled", info()), "已取消");
  assert.equal(statusLine("failed", info({ error_summary: "平台被限流" })), "平台被限流");
});

test("statusLine: running 不显示耗时", () => {
  const line = statusLine("running", info({
    timings: { spawn_ms: 100, first_result_ms: null, total_ms: null },
  }));
  assert.equal(line, "正在检索…");
});
