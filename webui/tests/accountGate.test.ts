/**
 * 搜索前账号操作闸门测试（Round 18）—— 直接 import 生产模块
 * （webui/src/lib/accountGate.ts），不复制任何生产逻辑。
 *
 * 覆盖：busy 判定、空闲时不引入额外延迟、忙碌时等到空闲、超时返回 false、
 * 探测失败时失败开放（绝不把用户的搜索卡住）。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  ACCOUNT_GATE_POLL_MS,
  ACCOUNT_GATE_TIMEOUT_MS,
  accountOpsBusy,
  waitForAccountOpsIdle,
} from "../src/lib/accountGate.js";

// ── accountOpsBusy ─────────────────────────────────────────────────────

test("accountOpsBusy：syncing / verifying 视为占用 profile", () => {
  assert.equal(accountOpsBusy([{ platform: "xhs", status: "syncing" }]), true);
  assert.equal(accountOpsBusy([{ platform: "xhs", status: "verifying" }]), true);
});

test("accountOpsBusy：终态与未同步状态都不占用", () => {
  for (const status of ["connected", "unverified", "expired", "disconnected",
                        "failed", "unavailable"]) {
    assert.equal(accountOpsBusy([{ platform: "xhs", status }]), false, status);
  }
});

test("accountOpsBusy：null / 空数组不占用", () => {
  assert.equal(accountOpsBusy(null), false);
  assert.equal(accountOpsBusy(undefined), false);
  assert.equal(accountOpsBusy([]), false);
});

test("accountOpsBusy：任一平台占用即占用", () => {
  assert.equal(accountOpsBusy([
    { platform: "xhs", status: "connected" },
    { platform: "zhihu", status: "verifying" },
  ]), true);
});

// ── waitForAccountOpsIdle ──────────────────────────────────────────────

/** 受控时钟 + 计数：不依赖真实计时器。 */
function harness(responses: readonly (readonly { platform: string; status: string }[])[]) {
  let now = 0;
  let calls = 0;
  return {
    get calls() { return calls; },
    get now() { return now; },
    options: {
      timeoutMs: ACCOUNT_GATE_TIMEOUT_MS,
      pollMs: ACCOUNT_GATE_POLL_MS,
      now: () => now,
      sleep: async (ms: number) => { now += ms; },
      fetchAccounts: async () => {
        const r = responses[Math.min(calls, responses.length - 1)];
        calls += 1;
        return r;
      },
    },
  };
}

test("waitForAccountOpsIdle：一开始就空闲 → 立即放行，不 sleep", async () => {
  const h = harness([[{ platform: "xhs", status: "connected" }]]);
  assert.equal(await waitForAccountOpsIdle(h.options), true);
  assert.equal(h.calls, 1);
  assert.equal(h.now, 0);
});

test("waitForAccountOpsIdle：忙碌 → 等到变空闲", async () => {
  const h = harness([
    [{ platform: "xhs", status: "syncing" }],
    [{ platform: "xhs", status: "verifying" }],
    [{ platform: "xhs", status: "connected" }],
  ]);
  assert.equal(await waitForAccountOpsIdle(h.options), true);
  assert.equal(h.calls, 3);
  assert.equal(h.now, ACCOUNT_GATE_POLL_MS * 2);
});

test("waitForAccountOpsIdle：一直忙碌 → 超时返回 false（后端 409 兜底）", async () => {
  const h = harness([[{ platform: "xhs", status: "syncing" }]]);
  assert.equal(await waitForAccountOpsIdle(h.options), false);
  assert.ok(h.now >= ACCOUNT_GATE_TIMEOUT_MS);
});

test("waitForAccountOpsIdle：探测抛异常 → 失败开放，立即放行", async () => {
  let calls = 0;
  const allowed = await waitForAccountOpsIdle({
    now: () => 0,
    sleep: async () => {},
    fetchAccounts: async () => { calls += 1; throw new Error("api down"); },
  });
  assert.equal(allowed, true);
  assert.equal(calls, 1);
});

test("waitForAccountOpsIdle：探测返回 null（未加载）不阻塞搜索", async () => {
  const allowed = await waitForAccountOpsIdle({
    now: () => 0,
    sleep: async () => {},
    fetchAccounts: async () => null,
  });
  assert.equal(allowed, true);
});
