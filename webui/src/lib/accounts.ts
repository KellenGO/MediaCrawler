/**
 * 账号状态汇总（Round 14.2，无 React 依赖）。
 *
 * 顶部"登录状态 · N/4"只统计真实已验证登录：
 *   status === "connected" && verified === true
 * unverified + profile_exists 只表示"本地已导入会话，可尝试公开搜索"，
 * 绝不冒充已验证登录、绝不计入登录数量（Round 14.2 修正）。
 *
 * 本模块同时提供：
 * - 登录徽章状态推导（检查中 / 暂不可用 / N/M 及色调）；
 * - 登录失效事件推导与去重（"B站登录状态已失效"只弹一次）；
 * - 未登录平台一次性低干扰提示。
 *
 * 注意：DOM contains、toast 触发时机等属于组件接线（Header.tsx），
 * 本模块只提供纯状态转换与模块级去重存储。
 *
 * 注意：此处使用相对导入（而非 @/ 别名），保证 node:test 编译产物
 * 也能在运行时解析（tsc 不会重写路径别名；.js 后缀是 ESM 运行时要求）。
 */

import { PLATFORM_LABELS } from "../types/search.js";
import type { PlatformSlug } from "../types/search.js";

export interface PlatformDiagnostic {
  platform: PlatformSlug;
  search_available: boolean;
  search_mode: "fast_path" | "browser_fallback" | "api" | "page" | "unavailable" | null;
  account_state: string;
  /** User-visible snippet capability; separate from detail hydration. */
  snippet_available?: boolean | null;
  hydration_available: boolean | null;
  fallback_active: boolean;
  limitation_code: string | null;
  user_message: string | null;
  recommended_action: string | null;
  checked_at: string | null;
}

/** 与后端 GET /api/search/accounts 返回的账号条目字段一致（窄接口）。 */
export interface AccountStatusInfo {
  platform: string;
  profile_exists: boolean;
  status: string;
  verified: boolean;
  display_name: string | null;
  last_verified_at: string | null;
  safe_error_code: string | null;
  safe_message: string | null;
  browser_backend: string | null;
  diagnostic?: PlatformDiagnostic | null;
}

export type DiagnosticTone = "normal" | "available" | "limited" | "unavailable";

export function diagnosticTone(
  diagnostic: Pick<PlatformDiagnostic, "search_available" | "snippet_available" | "fallback_active">,
): DiagnosticTone {
  if (!diagnostic.search_available) return "unavailable";
  // A search-time snippet is enough for the user-facing capability. Do not
  // label a platform as limited merely because it has no detail hydrator.
  if (diagnostic.snippet_available === false) return "limited";
  if (diagnostic.fallback_active) return "available";
  return "normal";
}

export function diagnosticToneLabel(tone: DiagnosticTone): string {
  if (tone === "normal") return "正常";
  if (tone === "available") return "搜索可用";
  if (tone === "limited") return "部分能力受限";
  return "不可用";
}

export function diagnosticSearchModeLabel(mode: PlatformDiagnostic["search_mode"]): string {
  if (mode === "fast_path") return "快速路径";
  if (mode === "browser_fallback") return "浏览器备用路径";
  if (mode === "api") return "接口路径";
  if (mode === "page") return "页面路径";
  if (mode === "unavailable") return "当前不可用";
  return "—";
}

/**
 * 账号状态的基础文案 —— 状态集合的**唯一枚举来源**。
 *
 * 三处语境（账号设置页卡片 / 卡片里的诊断行 / 顶栏登录浮层）在此之上做少量
 * 措辞覆盖，避免状态集合散落在多个表里各自漂移（历史上同一状态出现过
 * "已导入，未确认登录" 与 "未验证" 两种文案）。
 */
const ACCOUNT_STATUS_LABELS: Record<string, string> = {
  connected: "已验证",
  unverified: "未验证",
  expired: "会话失效",
  failed: "同步失败",
  unavailable: "验证暂不可用",
  verifying: "验证中",
  syncing: "同步中",
  disconnected: "未同步",
};

/** 诊断行的状态文案（与基础文案一致）。 */
export function diagnosticAccountStateLabel(state: string): string {
  return ACCOUNT_STATUS_LABELS[state] || "状态未知";
}

/**
 * 账号卡上的状态文案（账号设置页卡片语境）。
 *
 * Round 17.2：unavailable + 小红书风控（461/471）→ "验证请求受限"。
 * 卡片语境与浮层语境措辞不同（卡片要说明"已导入但未确认登录"），
 * 但特例判定与状态集合统一在本模块维护。
 */
export function accountCardStatusLabel(acc: {
  status: string;
  safe_error_code?: string | null;
}): string {
  if (acc.status === "unavailable"
      && acc.safe_error_code === "login_verification_rate_limited") {
    return "验证请求受限";
  }
  const cardOverrides: Record<string, string> = {
    connected: "已连接",
    unverified: "已导入，未确认登录",
    failed: "失败",
  };
  return cardOverrides[acc.status] || ACCOUNT_STATUS_LABELS[acc.status] || acc.status;
}

export type AccountTone = "ok" | "warn" | "bad" | "idle";

/** 真实验证登录判定：仅 connected + verified（登录数量的唯一依据）。 */
export function isAccountVerified(
  acc: Pick<AccountStatusInfo, "status" | "verified">
): boolean {
  return acc.status === "connected" && acc.verified === true;
}

/** 展示语义分级：unverified + profile_exists 是"可公开搜索"提示（warn），
 *  绝不返回 ok（不显示绿色全正常）。 */
export function accountTone(
  acc: Pick<AccountStatusInfo, "status" | "verified" | "profile_exists">
): AccountTone {
  if (isAccountVerified(acc)) return "ok";
  if (acc.status === "unverified") return "warn"; // 含 profile_exists 场景
  if (acc.status === "expired") return "bad";
  if (acc.status === "failed") return "bad";
  if (acc.status === "unavailable") return "warn";
  if (acc.status === "syncing" || acc.status === "verifying") return "idle";
  return "idle"; // disconnected / 未知
}

export interface AccountSummary {
  /** 真实已验证登录的平台数（connected + verified）。 */
  verified: number;
  /** 平台总数（通常为 4）。 */
  total: number;
  /** 已导入但未确认登录的平台数。 */
  unverified: number;
  /** 验证暂不可用的平台数。 */
  unavailable: number;
}

/** 汇总：verified 只统计 isAccountVerified。 */
export function summarizeAccounts(
  accounts: readonly Pick<AccountStatusInfo, "status" | "verified">[]
): AccountSummary {
  return {
    verified: accounts.filter(isAccountVerified).length,
    total: accounts.length,
    unverified: accounts.filter((a) => a.status === "unverified").length,
    unavailable: accounts.filter((a) => a.status === "unavailable").length,
  };
}

/** 平台状态在浮层中的一行文案（"可公开搜索"保留，但不计入登录数量）。
 *  Round 17.2: unavailable + login_verification_rate_limited（小红书
 *  461/471 风控）→ "验证受限"；普通 unavailable 仍为"验证暂不可用"。 */
export function accountSummaryLabel(
  acc: Pick<
    AccountStatusInfo,
    "status" | "verified" | "profile_exists" | "safe_error_code"
  >
): string {
  if (acc.status === "connected" && acc.verified) return "已连接";
  if (acc.status === "unverified" && acc.profile_exists) return "可公开搜索";
  if (acc.status === "unverified") return "尚未验证";
  if (acc.status === "expired") return "会话失效";
  if (acc.status === "failed") return "同步失败";
  if (acc.status === "unavailable") {
    if (acc.safe_error_code === "login_verification_rate_limited") {
      return "验证受限";
    }
    return "验证暂不可用";
  }
  if (acc.status === "syncing") return "同步中…";
  if (acc.status === "verifying") return "验证中…";
  return "未同步";
}

// ── 登录徽章（Header 顶部按钮）状态推导 ────────────────────────────────

export type LoginBadgeTone = "ok" | "warn" | "idle";

export type LoginBadge =
  | { kind: "checking" } // 首次加载中：登录状态 · 检查中
  | { kind: "unavailable" } // 首次加载失败 / API 不可用：登录状态 · 暂不可用
  | { kind: "summary"; verified: number; total: number; tone: LoginBadgeTone; stale: boolean };

export interface AccountsLoadState {
  /** 首次加载进行中（健康检查或首次账号请求未决）。 */
  loading: boolean;
  /** 是否曾成功加载过账号列表。 */
  initialLoaded: boolean;
  /** 最近一次请求失败（曾成功时可保留旧数据，由 stale 区分）。 */
  error: boolean;
}

/**
 * Header 徽章状态：
 * - 从未成功加载 + error → unavailable（暂不可用）；
 * - 从未成功加载（等待中）→ checking（检查中）；
 * - 已加载 → verified/total，全部 verified 才 ok（绿）；部分 → warn（橙）；
 *   0 个 → idle（灰）；当前刷新失败 → stale（旧数据，灰化）。
 */
export function loginBadgeFrom(
  accounts: readonly Pick<AccountStatusInfo, "status" | "verified">[] | null,
  load: AccountsLoadState
): LoginBadge {
  if (!accounts || !load.initialLoaded) {
    if (load.error) return { kind: "unavailable" };
    return { kind: "checking" };
  }
  const s = summarizeAccounts(accounts);
  let tone: LoginBadgeTone;
  if (s.total > 0 && s.verified === s.total) tone = "ok";
  else if (s.verified > 0) tone = "warn";
  else tone = "idle";
  return {
    kind: "summary",
    verified: s.verified,
    total: s.total,
    tone,
    stale: load.error,
  };
}

// ── 登录失效事件（connected → expired/login_required）─────────────────

export interface LoginExpiryEvent {
  platform: string;
  label: string; // 平台显示名，如 "B站"
  lastVerifiedAt: string | null; // 失效前最后一次验证时间（toast 去重签名）
}

/** 从 prev → next 推导"由已验证降为 expired/login_required"的平台事件。 */
export function loginExpiryEvents(
  prev: readonly AccountStatusInfo[] | null,
  next: readonly AccountStatusInfo[] | null
): LoginExpiryEvent[] {
  if (!prev || !next) return [];
  const prevVerified = new Map<string, AccountStatusInfo>();
  for (const a of prev) {
    if (isAccountVerified(a)) prevVerified.set(a.platform, a);
  }
  const events: LoginExpiryEvent[] = [];
  for (const acc of next) {
    const was = prevVerified.get(acc.platform);
    if (!was) continue;
    if (isAccountVerified(acc)) continue;
    const isLoginExpiry =
      acc.status === "expired" || acc.safe_error_code === "login_required";
    if (!isLoginExpiry) continue;
    events.push({
      platform: acc.platform,
      label: PLATFORM_LABELS[acc.platform as PlatformSlug] || acc.platform,
      lastVerifiedAt: was.last_verified_at,
    });
  }
  return events;
}

/** toast 去重签名：同一平台 + 同一失效前验证时间 → 同一签名 → 只提醒一次。 */
export function loginExpiryToastKey(
  platform: string,
  lastVerifiedAt: string | null
): string {
  return `${platform}:${lastVerifiedAt ?? "?"}`;
}

/** 过滤掉已提醒过的失效事件（相同状态签名不重复提醒）。 */
export function pendingLoginExpiryNotices(
  events: readonly LoginExpiryEvent[],
  notifiedKeys: ReadonlySet<string>
): LoginExpiryEvent[] {
  return events.filter(
    (e) => !notifiedKeys.has(loginExpiryToastKey(e.platform, e.lastVerifiedAt))
  );
}

/** 未登录（unverified）平台数："有 N 个平台尚未确认登录"提示用。 */
export function unverifiedWarningCount(
  accounts: readonly Pick<AccountStatusInfo, "status">[] | null
): number {
  if (!accounts) return 0;
  return accounts.filter((a) => a.status === "unverified").length;
}

// ── 页面生命周期级去重（模块级：React StrictMode 双挂载下也不重复） ──

const LOGIN_EXPIRY_NOTIFIED: Set<string> = new Set();
const UNVERIFIED_WARNING_SHOWN = { shown: false };

export function wasLoginExpiryNotified(key: string): boolean {
  return LOGIN_EXPIRY_NOTIFIED.has(key);
}

export function markLoginExpiryNotified(key: string): void {
  LOGIN_EXPIRY_NOTIFIED.add(key);
}

/** 一次性消费"未登录平台"提示；同一次页面生命周期只允许一次。 */
export function consumeUnverifiedWarning(): boolean {
  if (UNVERIFIED_WARNING_SHOWN.shown) return false;
  UNVERIFIED_WARNING_SHOWN.shown = true;
  return true;
}

/** 仅测试用：复位模块级去重存储（生产代码不调用）。 */
export function resetAccountNoticeStateForTests(): void {
  LOGIN_EXPIRY_NOTIFIED.clear();
  UNVERIFIED_WARNING_SHOWN.shown = false;
}
