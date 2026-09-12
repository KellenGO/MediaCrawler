/**
 * 浏览器扩展会话同步协议（无 React 依赖）。
 *
 * 把原来内联在 AccountsPage 里的协议知识集中到这里，供两处复用：
 * - AccountsPage：用户手动"一键同步四个平台"；
 * - useAutoAccountSync：打开程序时自动检测并同步（Round 18）。
 *
 * 协议约定见 browser_extension/README.md：
 * 1. 网页向后端申请一次性 sync-ticket；
 * 2. 网页通过 window.postMessage 只把 ticket / platform / request_id 交给
 *    content script（Cookie 绝不经过网页 JavaScript）；
 * 3. service worker 直接 fetch 到本地后端完成导入。
 *
 * 本模块不持有任何 Cookie：只转发票据与 request_id，响应里也只有安全字段。
 */

import axios from "axios";

import type { PlatformSlug } from "../types/search.js";
import type { SyncAttemptOutcome, BulkSyncBlockReason } from "./accountBulkSync.js";

/** 与 browser_extension/sync_protocol.js 的 EXTENSION_PROTOCOL_VERSION 一致。 */
export const EXTENSION_PROTOCOL_VERSION = 2;

/**
 * 最低可用的扩展版本（manifest 1.1.3 起 ready/pong 才携带真实
 * extension_version，网页才能区分 Round 8 的旧脚本）。
 */
export const EXTENSION_MIN_VERSION = "1.1.3";

/**
 * 扩展响应超时。后端账号服务在导入后会做有界验证
 * （SYNC_VERIFY_TIMEOUT_SECONDS），加上 Cookie 读取、导入和网络往返，
 * 前端超时绝不能短于后端 —— 否则会先于后端报"扩展未响应"。
 */
export const SYNC_RESPONSE_TIMEOUT_MS = 70000;

/**
 * 探测扩展的总窗口与重复间隔。
 *
 * 必须**反复**发 ping，不能只发一次：扩展的 content script 是
 * ``run_at: document_idle`` 注入的，可能晚于 React 挂载并发出第一次 ping ——
 * 单次 ping 会石沉大海，把已安装的扩展误判成"未安装"，自动同步就永远不会
 * 启动。（账号页是懒加载 chunk、挂载较晚，掩盖了这个竞态。）
 */
export const EXTENSION_PROBE_TOTAL_MS = 6000;
export const EXTENSION_PROBE_INTERVAL_MS = 400;

/** @deprecated 用 EXTENSION_PROBE_TOTAL_MS；保留导出避免旧引用断裂。 */
export const EXTENSION_PROBE_TIMEOUT_MS = EXTENSION_PROBE_TOTAL_MS;

export const ACCOUNTS_API_BASE = "/api/search/accounts";

/** 扩展 sync-response 携带的安全字段（无任何 Cookie 值）。 */
export interface SyncResult {
  success: boolean;
  verified: boolean;
  status: string;
  safe_error_code: string;
  safe_message: string;
  sync_stage: string;
  received_cookie_count: number | null;
  accepted_cookie_count: number | null;
  skipped_cookie_count: number | null;
  required_cookie_present: boolean | null;
  /** 白名单登录标记的布尔诊断（仅名称+true/false，无 Cookie 值）。 */
  login_marker_presence: Record<string, boolean> | null;
}

export type ExtensionState =
  | "checking"
  | "connected"
  | "outdated"
  | "not-installed"
  | "unknown";

export interface ExtensionProbe {
  state: "connected" | "outdated" | "not-installed";
  version: string;
}

/** semver 三段比较："1.1.3" >= "1.1.2" → true。非字符串视为不可用。 */
export function versionAtLeast(v: unknown, min: string): boolean {
  if (typeof v !== "string" || !v) return false;
  const a = v.split(".").map((s) => parseInt(s, 10) || 0);
  const b = min.split(".").map((s) => parseInt(s, 10) || 0);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const x = a[i] ?? 0;
    const y = b[i] ?? 0;
    if (x !== y) return x > y;
  }
  return true;
}

/** 由 pong 的协议版本 + 扩展版本推导扩展状态（纯函数，供测试）。 */
export function classifyExtensionProbe(
  protocolVersion: unknown,
  extensionVersion: unknown
): "connected" | "outdated" {
  const proto = Number(protocolVersion);
  const ver = typeof extensionVersion === "string" ? extensionVersion : "";
  return proto === EXTENSION_PROTOCOL_VERSION
    && versionAtLeast(ver, EXTENSION_MIN_VERSION)
    ? "connected"
    : "outdated";
}

/**
 * 探测扩展是否安装且版本可用：反复向 content script 发 ping 直到收到 pong，
 * 超过总窗口仍未收到才判定"未安装"。
 *
 * 为什么必须重试：content script 以 ``document_idle`` 注入，可能晚于应用挂载
 * 和第一次 ping。只发一次会误判（见 EXTENSION_PROBE_TOTAL_MS 的注释）。
 */
export function detectExtension(
  opts?: { totalMs?: number; intervalMs?: number }
): Promise<ExtensionProbe> {
  const totalMs = opts?.totalMs ?? EXTENSION_PROBE_TOTAL_MS;
  const intervalMs = opts?.intervalMs ?? EXTENSION_PROBE_INTERVAL_MS;
  return new Promise((resolve) => {
    let settled = false;
    let poller: ReturnType<typeof setInterval> | null = null;
    let deadline: ReturnType<typeof setTimeout> | null = null;
    const finish = (probe: ExtensionProbe) => {
      if (settled) return;
      settled = true;
      window.removeEventListener("message", onMessage);
      if (poller) clearInterval(poller);
      if (deadline) clearTimeout(deadline);
      resolve(probe);
    };
    const onMessage = (event: MessageEvent) => {
      const msg = event.data;
      if (!msg || msg.source !== "mc-accounts" || msg.type !== "pong") return;
      finish({
        state: classifyExtensionProbe(
          msg.extension_protocol_version, msg.extension_version),
        version: typeof msg.extension_version === "string" ? msg.extension_version : "",
      });
    };
    window.addEventListener("message", onMessage);
    const ping = () => window.postMessage({ source: "mc-accounts", type: "ping" }, "*");
    ping();
    poller = setInterval(() => {
      if (settled) return;
      ping();
    }, intervalMs);
    deadline = setTimeout(
      () => finish({ state: "not-installed", version: "" }), totalMs);
  });
}

/**
 * 同步单个平台：申请票据 → 让扩展读取并上报当前浏览器的平台 Cookie。
 *
 * 返回 null 表示扩展超时未响应。票据申请失败（含后端 409 search_in_progress）
 * 会抛出，由调用方决定如何呈现 —— 调用方需要"搜索进行中"这类阻断语义。
 */
export async function requestPlatformSync(
  platform: PlatformSlug,
  opts?: { timeoutMs?: number }
): Promise<SyncResult | null> {
  const timeoutMs = opts?.timeoutMs ?? SYNC_RESPONSE_TIMEOUT_MS;
  // 1. 申请一次性票据
  const { data: ticketData } = await axios.post(
    `${ACCOUNTS_API_BASE}/sync-ticket`, { platform });
  const ticket: string = ticketData.ticket;
  // 2. 请求扩展同步
  const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  return await new Promise<SyncResult | null>((resolve) => {
    let settled = false;
    let timeout: ReturnType<typeof setTimeout> | null = null;
    const onMessage = (event: MessageEvent) => {
      const msg = event.data;
      if (!msg || msg.source !== "mc-accounts-response" || msg.type !== "sync-response") return;
      if (msg.request_id !== requestId) return;
      if (settled) return;
      settled = true;
      if (timeout) clearTimeout(timeout);
      window.removeEventListener("message", onMessage);
      resolve(msg as SyncResult);
    };
    timeout = setTimeout(() => {
      if (settled) return;
      settled = true;
      window.removeEventListener("message", onMessage);
      resolve(null);
    }, timeoutMs);
    window.addEventListener("message", onMessage);
    window.postMessage({
      source: "mc-accounts",
      type: "sync-request",
      ticket,
      platform,
      request_id: requestId,
    }, "*");
  });
}

/**
 * 把一次同步尝试收敛为批量同步结果（纯函数）。
 *
 * 与 AccountsPage 的呈现逻辑同源，但只保留"这次尝试算成功/失败/待确认"
 * 以及是否需要中断整个队列 —— 供打开程序时的自动同步汇总使用。
 *
 * Round 11 语义必须保持：只有 status==="connected" && verified===true 且无
 * 安全错误码才算"已验证"，unavailable（网络/风控）绝不冒充成功或未登录。
 */
export function mapSyncResultToOutcome(
  platform: PlatformSlug,
  result: SyncResult | null
): SyncAttemptOutcome {
  if (result === null) {
    return {
      platform, kind: "failed", success: false, verified: false,
      safeErrorCode: "extension_no_response",
      safeMessage: "扩展未在超时时间内响应。",
    };
  }
  if (!result.success) {
    const code = result.safe_error_code;
    return {
      platform, kind: "failed", success: false, verified: false,
      safeErrorCode: code || undefined,
      safeMessage: result.safe_message || undefined,
      ...(code === "search_in_progress"
        ? { blockQueue: "search_in_progress" as BulkSyncBlockReason } : {}),
    };
  }
  if (result.verified && result.status === "connected" && !result.safe_error_code) {
    return { platform, kind: "verified", success: true, verified: true };
  }
  if (result.status === "verifying") {
    return {
      platform, kind: "verifying", success: true, verified: false,
      safeMessage: result.safe_message || undefined,
    };
  }
  if (result.status === "unavailable"
      || result.safe_error_code === "login_verification_unavailable") {
    return {
      platform, kind: "unavailable", success: true, verified: false,
      safeErrorCode: result.safe_error_code || "login_verification_unavailable",
      safeMessage: result.safe_message || undefined,
    };
  }
  return {
    platform, kind: "imported", success: true, verified: false,
    safeErrorCode: result.safe_error_code || "login_not_verified",
    safeMessage: result.safe_message || undefined,
  };
}
