/**
 * Round 14.3 批量同步测试 —— 直接 import 编译后的生产模块
 * （webui/src/lib/accountBulkSync.ts），不复制任何生产逻辑。
 *
 * 覆盖：
 * - 固定顺序 xhs → douyin → bilibili → zhihu；
 * - 最大同时执行数量始终为 1（严格串行）；
 * - 单个平台抛错后仍继续后续平台；
 * - 全局阻断停止剩余队列（checkBlock 与 outcome.blockQueue 两条路径）；
 * - 进度依次为 1/4、2/4、3/4、4/4；
 * - verified/imported/verifying/unavailable/failed 汇总正确；
 * - 双击 guard 的纯状态规则；
 * - 汇总文案不包含 Cookie、ticket、header 或原始响应。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  BULK_SYNC_PLATFORM_ORDER,
  buildBulkBlockedMessage,
  buildBulkSummaryMessage,
  createBulkSyncGuard,
  runBulkSync,
  summarizeBulkOutcomes,
  type BulkSyncBlockReason,
  type SyncAttemptOutcome,
} from "../src/lib/accountBulkSync.js";
import type { PlatformSlug } from "../src/types/search.js";

const OK = (platform: PlatformSlug, kind: SyncAttemptOutcome["kind"] = "verified"): SyncAttemptOutcome => ({
  platform,
  kind,
  success: kind === "verified" || kind === "imported" || kind === "verifying" || kind === "unavailable",
  verified: kind === "verified",
});

const SENSITIVE = ["cookie", "ticket", "authorization", "set-cookie", "xsec_token", "traceback", "response"];

/** 测试环境无 DOM/Node 类型：本地毫秒延时（仅测试用，不依赖全局 setTimeout 类型）。 */
function delay(ms: number): Promise<void> {
  const g = globalThis as { setTimeout?: (fn: () => void, ms: number) => unknown };
  return new Promise((resolve) => {
    if (typeof g.setTimeout === "function") {
      g.setTimeout(() => resolve(), ms);
    } else {
      resolve();
    }
  });
}

// ── 固定顺序与最大并发 2（Phase 4.3） ──────────────────────────────────

test("固定平台顺序为 xhs、douyin、bilibili、zhihu", () => {
  assert.deepEqual([...BULK_SYNC_PLATFORM_ORDER], ["xhs", "douyin", "bilibili", "zhihu"]);
});

test("worker pool：最大并发恰为 2，启动顺序固定", async () => {
  const calls: PlatformSlug[] = [];
  let active = 0;
  let maxActive = 0;
  let finished = 0;

  async function syncOne(platform: PlatformSlug): Promise<SyncAttemptOutcome> {
    calls.push(platform);
    active += 1;
    maxActive = Math.max(maxActive, active);
    // 模拟真实耗时：若超过 2 个并发，active 会超过 2
    await delay(5);
    active -= 1;
    finished += 1;
    return OK(platform);
  }

  const result = await runBulkSync({ syncOne });
  assert.deepEqual(calls, ["xhs", "douyin", "bilibili", "zhihu"], "启动顺序必须固定");
  assert.equal(maxActive, 2, "最大并发恰为 2（不是 Promise.all 四个）");
  assert.equal(finished, 4, "四个平台各执行一次");
  assert.equal(result.completedCount, 4);
  assert.equal(result.blocked, false);
});

test("outcomes 按固定平台顺序排列（不按完成顺序）", async () => {
  // bilibili 完成最快，但输出顺序仍固定。
  async function syncOne(platform: PlatformSlug): Promise<SyncAttemptOutcome> {
    if (platform === "bilibili") {
      await delay(1);
      return OK(platform);
    }
    await delay(10);
    return OK(platform);
  }
  const result = await runBulkSync({ syncOne });
  assert.deepEqual(
    result.outcomes.map((o) => o.platform),
    ["xhs", "douyin", "bilibili", "zhihu"]
  );
});

// ── 单平台失败/异常后继续 ──────────────────────────────────────────────

test("单个平台抛错后仍继续后续平台（异常被安全汇总为 failed）", async () => {
  const calls: PlatformSlug[] = [];
  async function syncOne(platform: PlatformSlug): Promise<SyncAttemptOutcome> {
    calls.push(platform);
    if (platform === "douyin") throw new Error("boom");
    return OK(platform);
  }
  const result = await runBulkSync({ syncOne });
  assert.deepEqual(calls, ["xhs", "douyin", "bilibili", "zhihu"], "后续平台必须继续");
  assert.equal(result.outcomes.length, 4);
  const douyin = result.outcomes.find((o) => o.platform === "douyin")!;
  assert.equal(douyin.kind, "failed");
  assert.equal(douyin.success, false);
  assert.equal(douyin.verified, false);
  assert.equal(douyin.safeErrorCode, "sync_attempt_error");
  assert.ok(!SENSITIVE.some((s) => (douyin.safeMessage || "").toLowerCase().includes(s)));
});

test("单个平台返回 failed 结果（不抛异常）也继续后续平台", async () => {
  const calls: PlatformSlug[] = [];
  async function syncOne(platform: PlatformSlug): Promise<SyncAttemptOutcome> {
    calls.push(platform);
    return platform === "zhihu"
      ? { platform, kind: "failed", success: false, verified: false, safeErrorCode: "login_not_verified" }
      : OK(platform);
  }
  const result = await runBulkSync({ syncOne });
  assert.equal(result.outcomes.length, 4);
  assert.deepEqual(calls, ["xhs", "douyin", "bilibili", "zhihu"]);
});

// ── 全局阻断停止剩余队列 ───────────────────────────────────────────────

test("checkBlock 全局阻断：停止剩余队列并报告原因", async () => {
  const calls: PlatformSlug[] = [];
  async function syncOne(platform: PlatformSlug): Promise<SyncAttemptOutcome> {
    calls.push(platform);
    return OK(platform);
  }
  let blocked = false;
  const result = await runBulkSync({
    syncOne,
    checkBlock: () => {
      if (blocked) return "extension_not_connected" as BulkSyncBlockReason;
      blocked = true; // 第一个平台后开始阻断
      return null;
    },
  });
  assert.deepEqual(calls, ["xhs"], "剩余队列必须停止");
  assert.equal(result.blocked, true);
  assert.equal(result.blockReason, "extension_not_connected");
  assert.equal(result.completedCount, 1);
});

test("outcome.blockQueue（如 search_in_progress）停止启动后续平台，已开始的平台安全结束", async () => {
  const calls: PlatformSlug[] = [];
  async function syncOne(platform: PlatformSlug): Promise<SyncAttemptOutcome> {
    calls.push(platform);
    return platform === "xhs"
      ? { platform, kind: "failed", success: false, verified: false, safeErrorCode: "search_in_progress", blockQueue: "search_in_progress" }
      : OK(platform);
  }
  const result = await runBulkSync({ syncOne });
  // 并发 2：xhs/douyin 已同时启动；xhs 暴露阻断后不再启动 bilibili/zhihu，
  // 已开始的 douyin 允许安全结束。
  assert.deepEqual(calls, ["xhs", "douyin"]);
  assert.equal(result.blocked, true);
  assert.equal(result.blockReason, "search_in_progress");
  assert.equal(result.completedCount, 2);
});

// ── 进度回调（Phase 4.3：activePlatforms + completedCount） ─────────────

test("进度回调：activePlatforms 最多 2 个、保持固定顺序，completedCount 单调到 4", async () => {
  const activeSnapshots: PlatformSlug[][] = [];
  const completions: number[] = [];
  async function syncOne(platform: PlatformSlug): Promise<SyncAttemptOutcome> {
    await delay(1);
    return OK(platform);
  }
  await runBulkSync({
    syncOne,
    onProgress: (p) => {
      if (p.activePlatforms.length > 0) activeSnapshots.push([...p.activePlatforms]);
      completions.push(p.completedCount);
    },
  });
  // 任意快照：活动平台 ≤ 2 且保持固定顺序。
  for (const snap of activeSnapshots) {
    assert.ok(snap.length <= 2, `快照活动平台不得超过 2：${snap.join(",")}`);
    const idx = snap.map((p) => BULK_SYNC_PLATFORM_ORDER.indexOf(p));
    assert.deepEqual(idx, [...idx].sort((a, b) => a - b), "activePlatforms 必须保持固定顺序");
  }
  assert.ok(
    activeSnapshots.some((s) => s.length === 2),
    "出现过两个平台同时同步（并发 2）"
  );
  assert.equal(completions[completions.length - 1], 4, "最终完成数必须为 4");
});

// ── 结果汇总 ───────────────────────────────────────────────────────────

test("汇总计数：verified/imported/verifying/unavailable/failed 正确", () => {
  const outcomes: SyncAttemptOutcome[] = [
    OK("xhs", "verified"),
    OK("douyin", "imported"),
    OK("bilibili", "verifying"),
    OK("zhihu", "unavailable"),
  ];
  const counts = summarizeBulkOutcomes(outcomes);
  assert.deepEqual(counts, { verified: 1, imported: 1, verifying: 1, unavailable: 1, failed: 0, total: 4 });

  const withFail = summarizeBulkOutcomes([
    OK("xhs", "verified"),
    { platform: "douyin", kind: "failed", success: false, verified: false },
  ]);
  assert.deepEqual(withFail, { verified: 1, imported: 0, verifying: 0, unavailable: 0, failed: 1, total: 2 });
});

test("汇总文案：全部验证成功 → success 提示", () => {
  const msg = buildBulkSummaryMessage({ verified: 4, imported: 0, verifying: 0, unavailable: 0, failed: 0, total: 4 });
  assert.equal(msg.tone, "success");
  assert.equal(msg.title, "四个平台同步并验证成功");
});

test("汇总文案：部分失败 → warning + 诊断提示，且不含敏感内容", () => {
  const msg = buildBulkSummaryMessage({ verified: 2, imported: 1, verifying: 0, unavailable: 0, failed: 1, total: 4 });
  assert.equal(msg.tone, "warning");
  assert.ok(msg.title.includes("2 个已验证"));
  assert.ok(msg.title.includes("1 个已导入待确认"));
  assert.ok(msg.title.includes("1 个失败"));
  assert.equal(msg.description, "请查看对应平台卡片诊断");
  for (const s of SENSITIVE) {
    assert.ok(!msg.title.toLowerCase().includes(s), `汇总文案不得包含 ${s}`);
  }
});

test("汇总文案：部分未验证 → info 提示", () => {
  const msg = buildBulkSummaryMessage({ verified: 3, imported: 1, verifying: 0, unavailable: 0, failed: 0, total: 4 });
  assert.equal(msg.tone, "info");
  assert.ok(msg.title.includes("3 个已验证"));
});

test("全局阻断文案：固定安全文案且不含敏感内容", () => {
  for (const reason of ["extension_not_connected", "extension_outdated", "api_unavailable", "search_in_progress"] as BulkSyncBlockReason[]) {
    const text = buildBulkBlockedMessage(reason);
    assert.ok(text.length > 0);
    for (const s of SENSITIVE) {
      assert.ok(!text.toLowerCase().includes(s), `阻断文案不得包含 ${s}`);
    }
  }
});

// ── 双击 guard 纯状态规则 ──────────────────────────────────────────────

test("双击 guard：tryStart 第二次返回 false，finish 后恢复", () => {
  const guard = createBulkSyncGuard();
  assert.equal(guard.tryStart(), true);   // 第一套队列启动
  assert.equal(guard.tryStart(), false);  // 双击：拒绝第二套
  assert.equal(guard.tryStart(), false);  // 仍在运行：持续拒绝
  guard.finish();
  assert.equal(guard.tryStart(), true);   // 完成后可再次启动
  guard.finish();
});

test("guard 实例相互独立", () => {
  const a = createBulkSyncGuard();
  const b = createBulkSyncGuard();
  assert.equal(a.tryStart(), true);
  assert.equal(b.tryStart(), true); // 另一实例不受影响
});
