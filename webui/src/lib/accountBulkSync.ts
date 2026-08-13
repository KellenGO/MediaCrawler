/**
 * 批量同步四平台（Round 14.3，无 React 依赖）。
 *
 * 职责：
 * - 固定平台顺序：xhs → douyin → bilibili → zhihu；
 * - 严格串行：await 上一个平台完成才启动下一个（最大同时执行数量恒为 1）；
 * - 单个平台失败/异常 → 记录结构化结果，继续后续平台；
 * - 全局阻断（扩展未连接/过旧、API 不可用、搜索进行中）→ 停止剩余队列；
 * - 进度回调（1/4、2/4、3/4、4/4）；
 * - 结果汇总（不含 Cookie/ticket/header/响应体/traceback）。
 *
 * AccountsPage 必须调用本模块的 runBulkSync；测试也必须直接 import 本模块，
 * 不在测试里复制循环。
 */

import type { PlatformSlug } from "../types/search.js";

/** 固定平台顺序（一键同步与测试共用，禁止并行）。 */
export const BULK_SYNC_PLATFORM_ORDER: readonly PlatformSlug[] = [
  "xhs",
  "douyin",
  "bilibili",
  "zhihu",
];

/** 单平台同步结果（安全字段：不含 Cookie/ticket/header/响应体/traceback）。 */
export interface SyncAttemptOutcome {
  platform: PlatformSlug;
  kind: "verified" | "imported" | "verifying" | "unavailable" | "failed";
  success: boolean;
  verified: boolean;
  safeErrorCode?: string;
  safeMessage?: string;
  /** 该尝试暴露了全局阻断（如搜索进行中）：剩余队列应停止。 */
  blockQueue?: BulkSyncBlockReason;
}

/** 全局阻断类型：出现其一即停止剩余队列。 */
export type BulkSyncBlockReason =
  | "extension_not_connected"
  | "extension_outdated"
  | "api_unavailable"
  | "search_in_progress";

export interface BulkSyncProgress {
  /** 正在同步的平台；null 表示刚完成一个平台。 */
  currentPlatform: PlatformSlug | null;
  /** 已完成的平台数（0..4）。 */
  completedCount: number;
  totalCount: number;
}

export interface BulkSyncResult {
  outcomes: SyncAttemptOutcome[];
  /** 是否因全局阻断而提前停止。 */
  blocked: boolean;
  blockReason?: BulkSyncBlockReason;
  completedCount: number;
  totalCount: number;
}

export type SyncOneFn = (platform: PlatformSlug) => Promise<SyncAttemptOutcome>;
export type GlobalBlockCheckFn = () => BulkSyncBlockReason | null;
export type BulkProgressCallback = (progress: BulkSyncProgress) => void;

export interface BulkSyncOptions {
  syncOne: SyncOneFn;
  /** 每个平台开始前检查的全局阻断（扩展/API 状态等）。 */
  checkBlock?: GlobalBlockCheckFn;
  onProgress?: BulkProgressCallback;
}

/**
 * 串行批量同步：固定顺序、一次一个、单平台失败继续、全局阻断停止。
 */
export async function runBulkSync(options: BulkSyncOptions): Promise<BulkSyncResult> {
  const { syncOne, checkBlock, onProgress } = options;
  const outcomes: SyncAttemptOutcome[] = [];
  let blocked = false;
  let blockReason: BulkSyncBlockReason | undefined;
  const totalCount = BULK_SYNC_PLATFORM_ORDER.length;

  for (const platform of BULK_SYNC_PLATFORM_ORDER) {
    // 平台开始前：全局阻断检查（扩展/API 状态可能中途变化）。
    const blocker = checkBlock ? checkBlock() : null;
    if (blocker) {
      blocked = true;
      blockReason = blocker;
      break;
    }
    onProgress?.({ currentPlatform: platform, completedCount: outcomes.length, totalCount });

    let outcome: SyncAttemptOutcome;
    try {
      outcome = await syncOne(platform); // 严格串行：await 完成才进下一轮
    } catch (err) {
      // 单平台异常：记录安全失败，绝不透出原始错误细节。
      outcome = {
        platform,
        kind: "failed",
        success: false,
        verified: false,
        safeErrorCode: "sync_attempt_error",
        safeMessage: "同步失败，请查看该平台卡片诊断",
      };
    }
    outcomes.push(outcome);
    onProgress?.({ currentPlatform: null, completedCount: outcomes.length, totalCount });

    // 该平台暴露了全局阻断（例如同步票据返回 search_in_progress）→ 停止。
    if (outcome.blockQueue) {
      blocked = true;
      blockReason = outcome.blockQueue;
      break;
    }
  }

  return {
    outcomes,
    blocked,
    blockReason,
    completedCount: outcomes.length,
    totalCount,
  };
}

// ── 结果汇总（纯函数，供组件与测试共用）───────────────────────────────

export interface BulkOutcomeCounts {
  verified: number;
  imported: number;
  verifying: number;
  unavailable: number;
  failed: number;
  total: number;
}

/** 按 kind 汇总四个平台的结果。 */
export function summarizeBulkOutcomes(
  outcomes: readonly SyncAttemptOutcome[]
): BulkOutcomeCounts {
  const counts: BulkOutcomeCounts = {
    verified: 0,
    imported: 0,
    verifying: 0,
    unavailable: 0,
    failed: 0,
    total: outcomes.length,
  };
  for (const o of outcomes) {
    if (o.kind === "verified") counts.verified += 1;
    else if (o.kind === "imported") counts.imported += 1;
    else if (o.kind === "verifying") counts.verifying += 1;
    else if (o.kind === "unavailable") counts.unavailable += 1;
    else counts.failed += 1;
  }
  return counts;
}

export interface BulkSummaryMessage {
  tone: "success" | "warning" | "info";
  title: string;
  description?: string;
}

/** 汇总 toast 文案（仅由数量与固定文案构成，绝不包含敏感内容）。 */
export function buildBulkSummaryMessage(counts: BulkOutcomeCounts): BulkSummaryMessage {
  const { verified, imported, verifying, unavailable, failed, total } = counts;
  const pending = imported + verifying;
  if (total > 0 && verified === total) {
    return { tone: "success", title: "四个平台同步并验证成功" };
  }
  const parts = [
    `${verified} 个已验证`,
    `${pending} 个已导入待确认`,
  ];
  if (unavailable > 0) parts.push(`${unavailable} 个暂不可用`);
  if (failed > 0) parts.push(`${failed} 个失败`);
  if (failed > 0 || unavailable > 0) {
    return {
      tone: "warning",
      title: `同步完成：${parts.join("，")}`,
      description: "请查看对应平台卡片诊断",
    };
  }
  return { tone: "info", title: `同步完成：${parts.join("，")}` };
}

/** 全局阻断提示文案（固定安全文案）。 */
export function buildBulkBlockedMessage(reason: BulkSyncBlockReason | undefined): string {
  switch (reason) {
    case "extension_not_connected":
      return "未检测到浏览器扩展，已停止后续同步。请安装扩展并刷新本页后重试。";
    case "extension_outdated":
      return "扩展版本过旧，已停止后续同步。请在扩展管理页点击“重新加载”后刷新本页。";
    case "api_unavailable":
      return "本地 API 不可用，已停止后续同步。请确认后端已启动后重试。";
    case "search_in_progress":
      return "搜索正在进行，暂时不能同步账号，已停止后续同步。请等待搜索完成后重试。";
    default:
      return "同步已中断，请重试。";
  }
}

// ── 双击 guard（纯状态规则；组件用 ref 持有）──────────────────────────

/**
 * 批量同步双击 guard：单线程布尔锁。异步 React state 在双击间隔内可能
 * 尚未更新，因此必须用同步的 ref 锁 —— 本函数提供可测试的纯规则。
 */
export function createBulkSyncGuard(): {
  tryStart(): boolean;
  finish(): void;
} {
  let running = false;
  return {
    tryStart(): boolean {
      if (running) return false; // 已有一队列在跑：拒绝第二次启动
      running = true;
      return true;
    },
    finish(): void {
      running = false;
    },
  };
}
