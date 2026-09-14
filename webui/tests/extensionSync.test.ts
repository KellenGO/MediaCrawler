/**
 * 扩展同步协议测试（Round 18）—— 直接 import 生产模块
 * （webui/src/lib/extensionSync.ts）的纯函数部分，不复制任何生产逻辑。
 *
 * 不测 detectExtension / requestPlatformSync（需要真实 window 与扩展），
 * 它们的行为由 tests/test_webui_ui_contract.py 的接线契约与人工验证覆盖。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  EXTENSION_MIN_VERSION,
  EXTENSION_PROTOCOL_VERSION,
  SYNC_RESPONSE_TIMEOUT_MS,
  classifyExtensionProbe,
  mapSyncResultToOutcome,
  verifyResponseToSyncResult,
  versionAtLeast,
  type SyncResult,
} from "../src/lib/extensionSync.js";
import type { PlatformSlug } from "../src/types/search.js";

const PLATFORM: PlatformSlug = "xhs";

/** 成功响应样板：默认"已验证登录"。 */
function ok(over: Partial<SyncResult> = {}): SyncResult {
  return {
    success: true,
    verified: true,
    status: "connected",
    safe_error_code: "",
    safe_message: "",
    sync_stage: "completed",
    received_cookie_count: 10,
    accepted_cookie_count: 8,
    skipped_cookie_count: 2,
    required_cookie_present: true,
    login_marker_presence: { web_session: true },
    ...over,
  };
}

// ── versionAtLeast / classifyExtensionProbe ────────────────────────────

test("versionAtLeast：三段比较", () => {
  assert.equal(versionAtLeast("1.1.3", "1.1.3"), true);
  assert.equal(versionAtLeast("1.1.4", "1.1.3"), true);
  assert.equal(versionAtLeast("1.2.0", "1.1.3"), true);
  assert.equal(versionAtLeast("2.0.0", "1.1.3"), true);
  assert.equal(versionAtLeast("1.1.2", "1.1.3"), false);
  assert.equal(versionAtLeast("1.0.9", "1.1.3"), false);
});

test("versionAtLeast：缺失/非法版本视为不可用", () => {
  for (const bad of [undefined, null, "", 0, 113, {}, []]) {
    assert.equal(versionAtLeast(bad, "1.1.3"), false, String(bad));
  }
});

test("classifyExtensionProbe：协议与版本都满足才算 connected", () => {
  assert.equal(classifyExtensionProbe(EXTENSION_PROTOCOL_VERSION, EXTENSION_MIN_VERSION),
    "connected");
  // 旧脚本：协议相同但缺 extension_version（Round 8）→ outdated
  assert.equal(classifyExtensionProbe(EXTENSION_PROTOCOL_VERSION, undefined), "outdated");
  assert.equal(classifyExtensionProbe(EXTENSION_PROTOCOL_VERSION, "1.1.2"), "outdated");
  assert.equal(classifyExtensionProbe(1, "1.1.3"), "outdated");
  assert.equal(classifyExtensionProbe(undefined, "1.1.3"), "outdated");
});

test("超时足够长：不短于后端有界验证", () => {
  // 后端 SYNC_VERIFY_TIMEOUT_SECONDS=30；前端必须更宽，否则会先报"扩展未响应"
  assert.ok(SYNC_RESPONSE_TIMEOUT_MS >= 30_000);
});

// ── mapSyncResultToOutcome ─────────────────────────────────────────────

test("mapSyncResultToOutcome：connected+verified+无错误码 → verified", () => {
  const o = mapSyncResultToOutcome(PLATFORM, ok());
  assert.equal(o.kind, "verified");
  assert.equal(o.success, true);
  assert.equal(o.verified, true);
  assert.equal(o.blockQueue, undefined);
});

test("mapSyncResultToOutcome：扩展超时（null）→ failed", () => {
  const o = mapSyncResultToOutcome(PLATFORM, null);
  assert.equal(o.kind, "failed");
  assert.equal(o.verified, false);
  assert.equal(o.safeErrorCode, "extension_no_response");
});

test("mapSyncResultToOutcome：success=false → failed 且保留安全错误码", () => {
  const o = mapSyncResultToOutcome(PLATFORM, ok({
    success: false, verified: false, status: "failed",
    safe_error_code: "cookie_format_invalid", safe_message: "Cookie 格式不兼容",
  }));
  assert.equal(o.kind, "failed");
  assert.equal(o.safeErrorCode, "cookie_format_invalid");
  assert.equal(o.safeMessage, "Cookie 格式不兼容");
});

test("mapSyncResultToOutcome：search_in_progress → 中断整个队列", () => {
  const o = mapSyncResultToOutcome(PLATFORM, ok({
    success: false, verified: false, status: "failed",
    safe_error_code: "search_in_progress", safe_message: "正在搜索",
  }));
  assert.equal(o.kind, "failed");
  assert.equal(o.blockQueue, "search_in_progress");
});

test("mapSyncResultToOutcome：verifying（后台验证中）→ verifying", () => {
  const o = mapSyncResultToOutcome(PLATFORM, ok({
    verified: false, status: "verifying", safe_error_code: "",
  }));
  assert.equal(o.kind, "verifying");
  assert.equal(o.success, true);
  assert.equal(o.verified, false);
});

test("mapSyncResultToOutcome：unavailable 绝不冒充成功或未登录", () => {
  const o = mapSyncResultToOutcome(PLATFORM, ok({
    verified: false, status: "unavailable",
    safe_error_code: "login_verification_unavailable", safe_message: "当前无法验证",
  }));
  assert.equal(o.kind, "unavailable");
  assert.equal(o.verified, false);
  assert.equal(o.safeErrorCode, "login_verification_unavailable");
});

test("mapSyncResultToOutcome：success 但未验证 → imported（已导入待确认）", () => {
  const o = mapSyncResultToOutcome(PLATFORM, ok({
    verified: false, status: "unverified", safe_error_code: "",
  }));
  assert.equal(o.kind, "imported");
  assert.equal(o.success, true);
  assert.equal(o.verified, false);
  assert.equal(o.safeErrorCode, "login_not_verified");
});

test("mapSyncResultToOutcome：success 但带错误码 → 不冒充 verified", () => {
  const o = mapSyncResultToOutcome(PLATFORM, ok({
    verified: true, status: "connected", safe_error_code: "login_required",
  }));
  assert.notEqual(o.kind, "verified");
  assert.equal(o.verified, false);
});

// ── verify 端点响应 → SyncResult（不经过扩展的复核路径）───────────────

test("verifyResponseToSyncResult：验证通过映射为 connected/verified", () => {
  const r = verifyResponseToSyncResult({
    success: true, platform: "xhs", verified: true, status: "connected",
    safe_error_code: null, safe_message: "会话验证通过",
  });
  assert.equal(r.success, true);
  assert.equal(r.verified, true);
  assert.equal(r.status, "connected");
  assert.equal(r.sync_stage, "verification");
  const o = mapSyncResultToOutcome(PLATFORM, r);
  assert.equal(o.kind, "verified");
});

test("verifyResponseToSyncResult：不虚构同步专有字段（Cookie 计数一律 null）", () => {
  const r = verifyResponseToSyncResult({ success: true, verified: true, status: "connected" });
  assert.equal(r.received_cookie_count, null);
  assert.equal(r.accepted_cookie_count, null);
  assert.equal(r.skipped_cookie_count, null);
  assert.equal(r.required_cookie_present, null);
  assert.equal(r.login_marker_presence, null);
});

test("verifyResponseToSyncResult：unavailable 不冒充成功也不冒充未登录", () => {
  const o = mapSyncResultToOutcome(PLATFORM, verifyResponseToSyncResult({
    success: true, verified: false, status: "unavailable",
    safe_error_code: "login_verification_unavailable",
    safe_message: "当前无法验证登录状态，仍可尝试搜索或稍后重新验证",
  }));
  assert.equal(o.kind, "unavailable");
  assert.equal(o.verified, false);
});

test("verifyResponseToSyncResult：风控受限仍是 unavailable（不是未登录）", () => {
  const o = mapSyncResultToOutcome(PLATFORM, verifyResponseToSyncResult({
    success: true, verified: false, status: "unavailable",
    safe_error_code: "login_verification_rate_limited",
  }));
  assert.equal(o.kind, "unavailable");
  assert.notEqual(o.safeErrorCode, "login_required");
});

test("verifyResponseToSyncResult：明确未登录 → imported（会话在但没确认）", () => {
  const o = mapSyncResultToOutcome(PLATFORM, verifyResponseToSyncResult({
    success: true, verified: false, status: "unverified",
    safe_error_code: "login_not_verified",
  }));
  assert.equal(o.kind, "imported");
  assert.equal(o.verified, false);
});

test("verifyResponseToSyncResult：响应残缺/空值不抛错且不冒充成功", () => {
  for (const input of [null, undefined, {}, { status: 123, verified: "yes" }]) {
    const r = verifyResponseToSyncResult(input as never);
    assert.equal(typeof r.status, "string");
    assert.equal(r.verified, false);
    assert.equal(mapSyncResultToOutcome(PLATFORM, r).kind, "imported");
  }
});
