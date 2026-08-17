/**
 * Round 14.2 账号登录状态汇总测试 —— 直接 import 编译后的生产模块
 * （webui/src/lib/accounts.ts），不复制任何生产逻辑。
 *
 * 覆盖：
 * - connected+verified 才计入 verified（登录数量）；
 * - unverified+profile_exists 不计入（不冒充已验证登录）；
 * - 效果场景为 3/4，而不是错误的 4/4；
 * - loading/error/0/N/4 对应正确 Header 徽章状态；
 * - 由已验证降为 expired 的事件可正确生成提醒；
 * - 相同状态签名不重复提醒（模块级去重）。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  accountSummaryLabel,
  accountTone,
  consumeUnverifiedWarning,
  isAccountVerified,
  loginBadgeFrom,
  loginExpiryEvents,
  loginExpiryToastKey,
  markLoginExpiryNotified,
  pendingLoginExpiryNotices,
  resetAccountNoticeStateForTests,
  summarizeAccounts,
  unverifiedWarningCount,
  wasLoginExpiryNotified,
  type AccountStatusInfo,
} from "../src/lib/accounts.js";

function acc(overrides: Partial<AccountStatusInfo>): AccountStatusInfo {
  return {
    platform: "xhs",
    profile_exists: false,
    status: "disconnected",
    verified: false,
    display_name: null,
    last_verified_at: null,
    safe_error_code: null,
    safe_message: null,
    browser_backend: null,
    ...overrides,
  };
}

// ── 登录数量定义：仅 connected + verified ──────────────────────────────

test("isAccountVerified: 仅 connected + verified 为真", () => {
  assert.equal(isAccountVerified({ status: "connected", verified: true }), true);
  assert.equal(isAccountVerified({ status: "connected", verified: false }), false);
  assert.equal(isAccountVerified({ status: "unverified", verified: true }), false);
  assert.equal(isAccountVerified({ status: "unverified", verified: false }), false);
  assert.equal(isAccountVerified({ status: "expired", verified: false }), false);
  assert.equal(isAccountVerified({ status: "unavailable", verified: false }), false);
});

test("accountTone: unverified + profile_exists → warn（不再是 ok，不显示绿色）", () => {
  assert.equal(accountTone({ status: "unverified", verified: false, profile_exists: true }), "warn");
  assert.equal(accountTone({ status: "unverified", verified: false, profile_exists: false }), "warn");
  assert.equal(accountTone({ status: "connected", verified: true, profile_exists: true }), "ok");
});

test("summarizeAccounts: unverified + profile_exists 不计入 verified", () => {
  const accounts = [
    acc({ platform: "xhs", status: "connected", verified: true, profile_exists: true }),
    acc({ platform: "douyin", status: "unverified", verified: false, profile_exists: true }), // 可公开搜索，非登录
    acc({ platform: "bilibili", status: "unverified", verified: false, profile_exists: true }),
    acc({ platform: "zhihu", status: "unverified", verified: false, profile_exists: true }),
  ];
  const summary = summarizeAccounts(accounts);
  assert.equal(summary.total, 4);
  assert.equal(summary.verified, 1); // 旧语义会算 4/4，Round 14.2 只算真实验证
  assert.equal(summary.unverified, 3);
});

test("summarizeAccounts: 效果场景 3/4（一个平台登录失效）", () => {
  const accounts = [
    acc({ platform: "xhs", status: "connected", verified: true, profile_exists: true }),
    acc({ platform: "douyin", status: "connected", verified: true, profile_exists: true }),
    acc({ platform: "bilibili", status: "expired", verified: false, profile_exists: true }),
    acc({ platform: "zhihu", status: "connected", verified: true, profile_exists: true }),
  ];
  const summary = summarizeAccounts(accounts);
  assert.equal(summary.total, 4);
  assert.equal(summary.verified, 3); // 3/4，而不是错误的 4/4
});

test("summarizeAccounts: 全验证 4/4；全未验证 0/4", () => {
  const allVerified = [
    acc({ status: "connected", verified: true }),
    acc({ status: "connected", verified: true }),
    acc({ status: "connected", verified: true }),
    acc({ status: "connected", verified: true }),
  ];
  assert.equal(summarizeAccounts(allVerified).verified, 4);

  const noneVerified = [
    acc({ status: "unverified", verified: false }),
    acc({ status: "expired", verified: false }),
    acc({ status: "disconnected", verified: false }),
    acc({ status: "unavailable", verified: false }),
  ];
  assert.equal(summarizeAccounts(noneVerified).verified, 0);
});

test("summarizeAccounts: 空数组 → 0/0", () => {
  const summary = summarizeAccounts([]);
  assert.equal(summary.verified, 0);
  assert.equal(summary.total, 0);
});

// ── Header 徽章状态（loginBadgeFrom）───────────────────────────────────

const VERIFIED4 = [
  acc({ platform: "xhs", status: "connected", verified: true }),
  acc({ platform: "douyin", status: "connected", verified: true }),
  acc({ platform: "bilibili", status: "connected", verified: true }),
  acc({ platform: "zhihu", status: "connected", verified: true }),
];
const VERIFIED3 = [
  acc({ platform: "xhs", status: "connected", verified: true }),
  acc({ platform: "douyin", status: "connected", verified: true }),
  acc({ platform: "bilibili", status: "expired", verified: false }),
  acc({ platform: "zhihu", status: "connected", verified: true }),
];
const VERIFIED0 = [
  acc({ platform: "xhs", status: "unverified", verified: false }),
  acc({ platform: "douyin", status: "unverified", verified: false }),
  acc({ platform: "bilibili", status: "disconnected", verified: false }),
  acc({ platform: "zhihu", status: "unavailable", verified: false }),
];

test("loginBadgeFrom: 首次加载中 → checking（检查中）", () => {
  const badge = loginBadgeFrom(null, { loading: true, initialLoaded: false, error: false });
  assert.deepEqual(badge, { kind: "checking" });
});

test("loginBadgeFrom: 首次请求失败 / API 不可用 → unavailable（暂不可用）", () => {
  const badge = loginBadgeFrom(null, { loading: false, initialLoaded: false, error: true });
  assert.deepEqual(badge, { kind: "unavailable" });
});

test("loginBadgeFrom: 全部验证 → ok（绿）4/4", () => {
  const badge = loginBadgeFrom(VERIFIED4, { loading: false, initialLoaded: true, error: false });
  assert.deepEqual(badge, { kind: "summary", verified: 4, total: 4, tone: "ok", stale: false });
});

test("loginBadgeFrom: 部分验证 → warn（橙）3/4", () => {
  const badge = loginBadgeFrom(VERIFIED3, { loading: false, initialLoaded: true, error: false });
  assert.deepEqual(badge, { kind: "summary", verified: 3, total: 4, tone: "warn", stale: false });
});

test("loginBadgeFrom: 0 个验证 → idle（灰，不显示绿色）", () => {
  const badge = loginBadgeFrom(VERIFIED0, { loading: false, initialLoaded: true, error: false });
  assert.deepEqual(badge, { kind: "summary", verified: 0, total: 4, tone: "idle", stale: false });
});

test("loginBadgeFrom: 曾经成功、当前刷新失败 → stale（保留旧数据但灰化）", () => {
  const badge = loginBadgeFrom(VERIFIED3, { loading: false, initialLoaded: true, error: true });
  assert.equal(badge.kind, "summary");
  if (badge.kind === "summary") assert.equal(badge.stale, true);
});

// ── 登录失效事件（connected → expired/login_required）──────────────────

test("loginExpiryEvents: connected → expired 生成事件（含平台显示名）", () => {
  const prev = [
    acc({ platform: "bilibili", status: "connected", verified: true, last_verified_at: "T1" }),
    acc({ platform: "xhs", status: "connected", verified: true }),
  ];
  const next = [
    acc({ platform: "bilibili", status: "expired", verified: false, safe_error_code: "login_required" }),
    acc({ platform: "xhs", status: "connected", verified: true }),
  ];
  const events = loginExpiryEvents(prev, next);
  assert.equal(events.length, 1);
  assert.equal(events[0].platform, "bilibili");
  assert.equal(events[0].label, "B站");
  assert.equal(events[0].lastVerifiedAt, "T1");
});

test("loginExpiryEvents: 仍验证 / 从未验证 / 无 prev → 无事件", () => {
  const prev = [
    acc({ platform: "xhs", status: "connected", verified: true }),
    acc({ platform: "douyin", status: "unverified", verified: false }),
  ];
  const next = [
    acc({ platform: "xhs", status: "connected", verified: true }), // 仍验证
    acc({ platform: "douyin", status: "expired", verified: false }), // 从未验证 → 不算降级
  ];
  assert.deepEqual(loginExpiryEvents(prev, next), []);
  assert.deepEqual(loginExpiryEvents(null, next), []);
  assert.deepEqual(loginExpiryEvents(prev, null), []);
});

test("loginExpiryEvents: rate_limited/failed 不生成登录失效事件", () => {
  const prev = [acc({ platform: "xhs", status: "connected", verified: true })];
  for (const status of ["rate_limited", "failed", "timed_out"]) {
    const next = [acc({ platform: "xhs", status, verified: false })];
    assert.deepEqual(loginExpiryEvents(prev, next), [], status);
  }
});

// ── 去重：相同状态签名不重复提醒 ───────────────────────────────────────

test("loginExpiryToastKey: 平台 + 失效前验证时间构成签名", () => {
  assert.equal(loginExpiryToastKey("bilibili", "T1"), "bilibili:T1");
  assert.notEqual(loginExpiryToastKey("bilibili", "T1"), loginExpiryToastKey("bilibili", "T2"));
  assert.notEqual(loginExpiryToastKey("bilibili", "T1"), loginExpiryToastKey("xhs", "T1"));
});

test("pendingLoginExpiryNotices: 已提醒的签名被过滤（相同签名不重复）", () => {
  const events = [
    { platform: "bilibili", label: "B站", lastVerifiedAt: "T1" },
    { platform: "xhs", label: "小红书", lastVerifiedAt: "T2" },
  ];
  const notified = new Set([loginExpiryToastKey("bilibili", "T1")]);
  const pending = pendingLoginExpiryNotices(events, notified);
  assert.equal(pending.length, 1);
  assert.equal(pending[0].platform, "xhs");
});

test("模块级去重：标记后同一签名不再提醒（StrictMode/轮询安全）", () => {
  resetAccountNoticeStateForTests();
  const key = loginExpiryToastKey("bilibili", "T1");
  assert.equal(wasLoginExpiryNotified(key), false);
  markLoginExpiryNotified(key);
  assert.equal(wasLoginExpiryNotified(key), true);
  // 相同签名第二次仍已提醒 → 组件侧不会再次 toast
  assert.equal(pendingLoginExpiryNotices(
    [{ platform: "bilibili", label: "B站", lastVerifiedAt: "T1" }],
    new Set([key]),
  ).length, 0);
});

// ── 未登录平台一次性提示 ───────────────────────────────────────────────

test("unverifiedWarningCount: 只统计 unverified", () => {
  const accounts = [
    acc({ platform: "xhs", status: "connected", verified: true }),
    acc({ platform: "douyin", status: "unverified", verified: false }),
    acc({ platform: "bilibili", status: "unverified", verified: false }),
    acc({ platform: "zhihu", status: "expired", verified: false }),
  ];
  assert.equal(unverifiedWarningCount(accounts), 2);
  assert.equal(unverifiedWarningCount(null), 0);
});

test("consumeUnverifiedWarning: 同一次页面生命周期只允许一次", () => {
  resetAccountNoticeStateForTests();
  assert.equal(consumeUnverifiedWarning(), true);
  assert.equal(consumeUnverifiedWarning(), false);
  assert.equal(consumeUnverifiedWarning(), false);
});

test("accountSummaryLabel: 浮层文案（可公开搜索保留，但不计入登录）", () => {
  assert.equal(accountSummaryLabel({ status: "connected", verified: true, profile_exists: true, safe_error_code: null }), "已连接");
  assert.equal(accountSummaryLabel({ status: "unverified", verified: false, profile_exists: true, safe_error_code: null }), "可公开搜索");
  assert.equal(accountSummaryLabel({ status: "unverified", verified: false, profile_exists: false, safe_error_code: null }), "尚未验证");
  assert.equal(accountSummaryLabel({ status: "expired", verified: false, profile_exists: true, safe_error_code: null }), "会话失效");
  assert.equal(accountSummaryLabel({ status: "failed", verified: false, profile_exists: true, safe_error_code: null }), "同步失败");
  assert.equal(accountSummaryLabel({ status: "unavailable", verified: false, profile_exists: false, safe_error_code: null }), "验证暂不可用");
  assert.equal(accountSummaryLabel({ status: "disconnected", verified: false, profile_exists: false, safe_error_code: null }), "未同步");
});

// ── Round 17.2: 小红书 461/471 风控（login_verification_rate_limited）────

test("accountSummaryLabel: 风控 unavailable → 验证受限；普通 unavailable → 验证暂不可用", () => {
  assert.equal(
    accountSummaryLabel({ status: "unavailable", verified: false, profile_exists: true, safe_error_code: "login_verification_rate_limited" }),
    "验证受限",
  );
  assert.equal(
    accountSummaryLabel({ status: "unavailable", verified: false, profile_exists: true, safe_error_code: "login_verification_unavailable" }),
    "验证暂不可用",
  );
});

test("summarizeAccounts: 风控 unavailable 不计入 verified", () => {
  const s = summarizeAccounts([
    acc({ platform: "xhs", status: "unavailable", verified: false, profile_exists: true, safe_error_code: "login_verification_rate_limited" }),
    acc({ platform: "douyin", status: "connected", verified: true, profile_exists: true }),
  ]);
  assert.equal(s.verified, 1); // 只有 douyin 计入
  assert.equal(s.unavailable, 1);
});

test("loginExpiryEvents: 风控 unavailable 不生成登录失效 toast", () => {
  const prev = [
    acc({ platform: "xhs", status: "connected", verified: true, last_verified_at: "T1" }),
  ];
  const next = [
    acc({ platform: "xhs", status: "unavailable", verified: false, profile_exists: true, safe_error_code: "login_verification_rate_limited", last_verified_at: null }),
  ];
  assert.deepEqual(loginExpiryEvents(prev, next), []);
});

test("accountTone: 风控 unavailable 不返回 ok（不显示绿色）", () => {
  assert.equal(
    accountTone({ status: "unavailable", verified: false, profile_exists: true }),
    "warn",
  );
});
