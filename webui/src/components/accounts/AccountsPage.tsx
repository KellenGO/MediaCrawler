import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, RefreshCw, Trash2, ExternalLink, Plug, ShieldCheck, ChevronDown, ChevronRight, Minus, Plus } from "lucide-react";
import { PLATFORM_LABELS, PLATFORM_COLORS } from "@/types/search";
import type { PlatformSlug } from "@/types/search";
import { invalidateAccounts, useAccounts } from "@/hooks/useAccounts";
import { usePlatformLimits } from "@/hooks/usePlatformLimits";
import { accountTone, type AccountTone } from "@/lib/accounts";
import { MAX_PLATFORM_LIMIT, MIN_PLATFORM_LIMIT, PLATFORM_ORDER, parsePlatformLimitInput } from "@/lib/platformLimits";
import {
  buildBulkBlockedMessage,
  buildBulkSummaryMessage,
  createBulkSyncGuard,
  runBulkSync,
  summarizeBulkOutcomes,
  type BulkSyncBlockReason,
  type SyncAttemptOutcome,
} from "@/lib/accountBulkSync";

interface LoginStatus {
  job_id: string;
  platform: string;
  status: string;
  message: string;
}

/** 扩展 sync-response 携带的安全字段（无任何 Cookie 值）。 */
interface SyncResult {
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

const API_BASE = "/api/search/accounts";

/** 与 browser_extension/sync_protocol.js 的 EXTENSION_PROTOCOL_VERSION 一致。 */
const EXTENSION_PROTOCOL_VERSION = 2;

/**
 * 最低可用的扩展版本（manifest 1.1.3 起 ready/pong 才携带真实
 * extension_version，网页才能区分 Round 8 的旧脚本）。
 */
const EXTENSION_MIN_VERSION = "1.1.3";

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

/**
 * 扩展响应超时。后端账号服务在导入后会做有界验证
 * （SYNC_VERIFY_TIMEOUT_SECONDS=45s），加上 Cookie 读取、导入和网络往返，
 * 前端超时绝不能短于后端 —— 否则会先于后端报"扩展未响应"。
 */
const SYNC_RESPONSE_TIMEOUT_MS = 70000;

const SYNC_STAGE_TEXT: Record<string, string> = {
  profile_import: "导入 Cookie",
  verification: "验证会话",
  completed: "已完成",
};

const PLATFORM_LOGIN_URLS: Record<string, string> = {
  xhs: "https://www.xiaohongshu.com",
  douyin: "https://www.douyin.com",
  bilibili: "https://www.bilibili.com",
  zhihu: "https://www.zhihu.com",
};

const STATUS_TEXT: Record<string, string> = {
  disconnected: "未同步",
  unverified: "已导入，未确认登录",
  syncing: "同步中",
  verifying: "验证中",
  connected: "已连接",
  expired: "会话失效",
  failed: "失败",
  unavailable: "验证暂不可用",
};

/** 账号卡状态文案（Round 17.2）：unavailable + 小红书风控（461/471）
 *  → "验证请求受限"；其他 unavailable 仍为"验证暂不可用"。 */
function accountStatusText(acc: {
  status: string;
  safe_error_code?: string | null;
}): string {
  if (acc.status === "unavailable"
      && acc.safe_error_code === "login_verification_rate_limited") {
    return "验证请求受限";
  }
  return STATUS_TEXT[acc.status] || acc.status;
}

/** 与后端 LOGIN_MARKER_NAMES 一致的白名单标记名（仅用于展示布尔值）。 */
const LOGIN_MARKERS: Record<string, string[]> = {
  xhs: ["web_session"],
  douyin: ["LOGIN_STATUS", "sessionid", "sessionid_ss"],
  bilibili: ["SESSDATA", "DedeUserID"],
  zhihu: ["z_c0", "d_c0"],
};

const BACKEND_TEXT: Record<string, string> = {
  chrome: "Chrome",
  edge: "Edge",
  playwright_chromium: "Playwright Chromium",
  custom: "自定义浏览器",
};

/** 平台字母标记（红 / 抖 / 哔 / 知）。 */
const PLATFORM_LETTERS: Record<string, string> = {
  xhs: "红",
  douyin: "抖",
  bilibili: "哔",
  zhihu: "知",
};

const TONE_BADGE: Record<AccountTone, string> = {
  ok: "bg-ok-soft text-[#3d7d60] border-ok/40",
  warn: "bg-warn-soft text-warn border-warn/40",
  bad: "bg-danger-soft text-danger border-danger/40",
  idle: "bg-cyber-bg-tertiary text-cyber-text-muted border-cyber-border-subtle",
};

/**
 * 单个平台的搜索数量设置行（Round 15）：
 * - 减号/加号不越过 1–20；
 * - 可直接编辑数字；输入框暂时为空时不立即变成 1；
 * - blur 或 Enter 校正：小于 1 → 1、大于 20 → 20、小数取整、非法/空 → 恢复上次有效值；
 * - 修改一个平台不影响其他平台。
 */
function LimitRow({
  platform,
  value,
  onChange,
}: {
  platform: PlatformSlug;
  value: number;
  onChange: (v: number) => void;
}) {
  const [draft, setDraft] = useState(String(value));
  const lastValidRef = useRef(value);

  useEffect(() => {
    setDraft(String(value));
    lastValidRef.current = value;
  }, [value]);

  const commit = (raw: string) => {
    const parsed = parsePlatformLimitInput(raw);
    if (parsed === null) {
      // 非法或空值 → 恢复该平台上一次有效值
      setDraft(String(lastValidRef.current));
      return;
    }
    lastValidRef.current = parsed;
    setDraft(String(parsed));
    onChange(parsed);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const raw = e.target.value;
    setDraft(raw);
    const parsed = parsePlatformLimitInput(raw);
    if (parsed !== null) {
      // 合法输入立即生效（自动保存）；空/非法等待 blur/Enter 校正
      lastValidRef.current = parsed;
      onChange(parsed);
    }
  };

  const color = PLATFORM_COLORS[platform] || "#4ca4dc";

  return (
    <div className="flex items-center gap-3 rounded-[14px] border border-cyber-border-subtle bg-cyber-bg-secondary px-3.5 py-3">
      <span
        className="w-[30px] h-[30px] rounded-[9px] grid place-items-center text-[13px] font-bold text-white flex-shrink-0"
        style={{ backgroundColor: color }}
      >
        {PLATFORM_LETTERS[platform]}
      </span>
      <span className="text-[13.5px] font-semibold text-cyber-text-primary min-w-[3.5rem]">
        {PLATFORM_LABELS[platform]}
      </span>
      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          aria-label={`减少${PLATFORM_LABELS[platform]}数量`}
          onClick={() => { const next = value - 1; if (next >= MIN_PLATFORM_LIMIT) onChange(next); }}
          disabled={value <= MIN_PLATFORM_LIMIT}
          className="w-8 h-8 grid place-items-center rounded-[9px] border border-cyber-border-subtle text-cyber-text-secondary hover:bg-cyber-bg-tertiary transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Minus className="w-4 h-4" />
        </button>
        <input
          type="text"
          inputMode="numeric"
          value={draft}
          onChange={handleChange}
          onBlur={() => commit(draft)}
          onKeyDown={(e) => { if (e.key === "Enter") e.currentTarget.blur(); }}
          aria-label={`${PLATFORM_LABELS[platform]}搜索数量`}
          className="w-14 h-9 text-center rounded-[9px] border border-cyber-border-subtle bg-cyber-bg-primary text-[13.5px] text-cyber-text-primary focus:outline-none focus:border-brand transition-colors"
        />
        <button
          type="button"
          aria-label={`增加${PLATFORM_LABELS[platform]}数量`}
          onClick={() => { const next = value + 1; if (next <= MAX_PLATFORM_LIMIT) onChange(next); }}
          disabled={value >= MAX_PLATFORM_LIMIT}
          className="w-8 h-8 grid place-items-center rounded-[9px] border border-cyber-border-subtle text-cyber-text-secondary hover:bg-cyber-bg-tertiary transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Plus className="w-4 h-4" />
        </button>
        <span className="text-[12.5px] text-cyber-text-muted w-4 flex-shrink-0">条</span>
        <span className="text-[11px] text-cyber-text-muted/70 w-9 flex-shrink-0 text-right">
          {MIN_PLATFORM_LIMIT}–{MAX_PLATFORM_LIMIT}
        </span>
      </div>
    </div>
  );
}

interface AccountsPageProps {
  onNavigateSearch?: () => void;
}

export function AccountsPage({ onNavigateSearch }: AccountsPageProps) {
  const { accounts, apiRunning } = useAccounts();
  // Phase 5.1: 账号 sync/verify/delete 完成后立即刷新共享缓存。
  const queryClient = useQueryClient();
  // Round 15: 每个平台独立搜索数量（localStorage 持久化，修改即保存）。
  const { limits, setLimit, resetAll } = usePlatformLimits();
  const [extensionState, setExtensionState] = useState<
    "checking" | "connected" | "outdated" | "not-installed" | "unknown"
  >("checking");
  const [busy, setBusy] = useState<Record<string, string>>({});
  const [lastDiag, setLastDiag] = useState<Record<string, SyncResult>>({});
  /** 诊断信息默认折叠（Round 14），用户点击"查看诊断"再展开。 */
  const [openDiag, setOpenDiag] = useState<Record<string, boolean>>({});
  const [auxOpen, setAuxOpen] = useState(false);
  const [auxPlatform, setAuxPlatform] = useState<string | null>(null);
  const [auxStatus, setAuxStatus] = useState<LoginStatus | null>(null);
  const extPong = useRef(false);
  const [extensionVersion, setExtensionVersion] = useState("");

  // ── 扩展检测（content script ping/pong）──────────────────────────────
  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      const msg = event.data;
      if (msg && msg.source === "mc-accounts" && msg.type === "pong") {
        extPong.current = true;
        const proto = Number(msg.extension_protocol_version);
        const ver = typeof msg.extension_version === "string" ? msg.extension_version : "";
        setExtensionVersion(ver);
        // 协议版本 2 只是兼容门；实际扩展版本必须 ≥ 1.1.3 —— 否则可能仍是
        // Round 8 旧脚本（协议同为 2，但 ready/pong 不带 extension_version，
        // 后端已引入的 login_marker_presence 等字段不会被正确转发）。
        setExtensionState(
          proto === EXTENSION_PROTOCOL_VERSION && versionAtLeast(ver, EXTENSION_MIN_VERSION)
            ? "connected" : "outdated");
      }
    };
    window.addEventListener("message", onMessage);
    window.postMessage({ source: "mc-accounts", type: "ping" }, "*");
    const t = setTimeout(() => {
      if (!extPong.current) setExtensionState("not-installed");
    }, 800);
    return () => {
      window.removeEventListener("message", onMessage);
      clearTimeout(t);
    };
  }, []);

  const setBusyPlatform = (platform: string | null, label = "") => {
    setBusy((prev) => {
      const next = { ...prev };
      if (platform) next[platform] = label;
      else Object.keys(next).forEach((k) => delete next[k]);
      return next;
    });
  };

  // 同步/验证期间保持 busy 状态，直到账号轮询看到终态才解除
  // （后端"正在导入/正在验证"可能持续数十秒，绝不能提前解除）。
  useEffect(() => {
    if (!accounts) return;
    const terminal = new Set(["disconnected", "unverified", "connected", "expired", "failed", "unavailable"]);
    setBusy((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const p of Object.keys(next)) {
        const a = accounts.find((x) => x.platform === p);
        if (a && terminal.has(a.status)) { delete next[p]; changed = true; }
      }
      return changed ? next : prev;
    });
  }, [accounts]);

  // ── 打开官方登录页（当前浏览器，绝不启动 Playwright）────────────────
  const openOfficial = useCallback((platform: string) => {
    window.open(PLATFORM_LOGIN_URLS[platform] || "https://www.xiaohongshu.com", "_blank");
  }, []);

  // ── 同步当前浏览器登录状态（Round 14.3：返回结构化结果，支持静默） ──
  // 单平台按钮调用 silent=false（保留现有 toast）；一键同步调用
  // silent=true（避免连续四组单平台 toast，最终只出一条汇总 toast）。
  const syncAccount = useCallback(
    async (platform: PlatformSlug, opts?: { silent?: boolean }): Promise<SyncAttemptOutcome> => {
      const silent = opts?.silent === true;
      // 安全失败结果（不含 Cookie/ticket/header/响应体/traceback）。
      const fail = (outcome: {
        safeErrorCode?: string; safeMessage?: string; blockQueue?: BulkSyncBlockReason;
      }): SyncAttemptOutcome => {
        if (!silent && outcome.safeMessage) toast.error(outcome.safeMessage);
        return {
          platform,
          kind: "failed",
          success: false,
          verified: false,
          safeErrorCode: outcome.safeErrorCode,
          safeMessage: outcome.safeMessage,
          blockQueue: outcome.blockQueue,
        };
      };

      if (extensionState === "not-installed") {
        return fail({
          safeErrorCode: "extension_not_installed",
          safeMessage: "未检测到浏览器扩展，请先安装（见页面底部安装说明）后刷新本页。",
        });
      }
      if (extensionState === "outdated") {
        // 禁止继续同步：旧脚本（1.1.2 及更早）协议同为 v2，但可能缺少
        // 后端需要的字段，继续同步会得到不可靠的诊断结果。
        return fail({
          safeErrorCode: "extension_outdated",
          safeMessage: "扩展版本过旧，请在 edge://extensions 点击\"重新加载\"后刷新本页再同步。",
        });
      }
      setBusyPlatform(platform, "syncing");
      try {
        // 1. 申请一次性票据
        const { data: ticketData } = await axios.post(`${API_BASE}/sync-ticket`, { platform });
        const ticket: string = ticketData.ticket;
        // 2. 请求扩展同步
        const requestId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const result = await new Promise<SyncResult | null>((resolve) => {
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
            resolve(msg);
          };
          timeout = setTimeout(() => {
            if (settled) return;
            settled = true;
            window.removeEventListener("message", onMessage);
            resolve(null);
          }, SYNC_RESPONSE_TIMEOUT_MS);
          window.addEventListener("message", onMessage);
          window.postMessage({
            source: "mc-accounts",
            type: "sync-request",
            ticket,
            platform,
            request_id: requestId,
          }, "*");
        });

        if (result === null) {
          setBusyPlatform(platform, "");
          const msg = `扩展 ${Math.round(SYNC_RESPONSE_TIMEOUT_MS / 1000)} 秒未响应。`
            + "请确认：1) 扩展已加载并启用；2) 已刷新本页（扩展注入后需刷新一次）；"
            + "3) 后端验证会话最长约 30 秒，若仍在验证可稍等后查看账号卡片诊断。";
          if (!silent) toast.error(msg);
          return {
            platform, kind: "failed", success: false, verified: false,
            safeErrorCode: "extension_no_response", safeMessage: msg,
          };
        }
        setLastDiag((prev) => ({ ...prev, [platform]: result }));
        // 同步不成功：显示后端/扩展返回的安全错误（可能是 Cookie 未读取到、
        // 格式不兼容、会话导入失败或正在搜索不能同步等）。
        if (!result.success) {
          setBusyPlatform(platform, "");
          const counts = typeof result.received_cookie_count === "number"
            ? `（读取 ${result.received_cookie_count} 条）` : "";
          const code = result.safe_error_code;
          const isSearchConflict = code === "search_in_progress";
          const msg = `同步失败${counts}：${result.safe_message || code || "未知错误"}`;
          if (!silent) toast.error(msg);
          return {
            platform, kind: "failed", success: false, verified: false,
            safeErrorCode: code || undefined,
            safeMessage: result.safe_message || undefined,
            ...(isSearchConflict ? { blockQueue: "search_in_progress" as const } : {}),
          };
        }
        // Round 11：success toast 只允许在真实验证通过时显示 ——
        // status==="connected" && verified===true && 无安全错误码。
        // （unavailable 等场景绝不显示"同步成功且登录验证通过"。）
        if (result.verified && result.status === "connected" && !result.safe_error_code) {
          setBusyPlatform(platform, "");
          const counts = typeof result.received_cookie_count === "number"
            ? `（读取 ${result.received_cookie_count} 条 / 接受 ${result.accepted_cookie_count ?? "?"} 条）` : "";
          if (!silent) toast.success(`同步成功且登录验证通过。${counts}`);
          return { platform, kind: "verified", success: true, verified: true };
        }
        const importedCounts = typeof result.received_cookie_count === "number"
          ? `（读取 ${result.received_cookie_count} 条 / 接受 ${result.accepted_cookie_count ?? "?"} 条）` : "";
        // 有界验证超时，验证仍在后台进行：busy 保持 "verifying"，直到账号
        // 轮询看到终态（见上面的 busy 清理 effect）。
        if (result.status === "verifying") {
          setBusyPlatform(platform, "verifying");
          const msg = `会话已导入，仍在后台验证 ${importedCounts}。可在本卡片查看诊断，或稍后点击"重新验证"确认结果。`;
          if (!silent) toast.info(msg);
          return { platform, kind: "verifying", success: true, verified: false, safeMessage: msg };
        }
        // Round 11：验证暂不可用（网络/超时/403 风控/导航失败）必须优先
        // 显示后端 safe_message，绝不落入下方"尚未确认账号登录"的提示
        // （那会错误地声称明确未登录）。
        if (result.status === "unavailable" || result.safe_error_code === "login_verification_unavailable") {
          setBusyPlatform(platform, "");
          const msg = result.safe_message || "当前无法验证登录状态，仍可尝试搜索或稍后重新验证";
          if (!silent) toast.warning(msg);
          return {
            platform, kind: "unavailable", success: true, verified: false,
            safeErrorCode: result.safe_error_code || "login_verification_unavailable",
            safeMessage: msg,
          };
        }
        // 明确未登录（expired / unverified）：已导入但未确认登录，这不是
        // 失败 —— 公开搜索仍可尝试。
        setBusyPlatform(platform, "");
        const msg = `会话已导入，但尚未确认账号登录。你仍可以尝试搜索；如搜索需要登录，再重新同步。${importedCounts}`;
        if (!silent) toast.info(msg);
        return {
          platform, kind: "imported", success: true, verified: false,
          safeErrorCode: result.safe_error_code || "login_not_verified",
          safeMessage: msg,
        };
      } catch (e) {
        setBusyPlatform(platform, "");
        // 解析后端结构化错误（safe_message / detail），而不是统一显示"API 可能未启动"
        const resp = (e as { response?: { status?: number; data?: { safe_message?: string; detail?: string; safe_error_code?: string } } }).response;
        const status = resp?.status;
        const code = resp?.data?.safe_error_code;
        const msg = resp?.data?.safe_message || resp?.data?.detail;
        const finalMsg = msg
          ? `同步请求失败：${msg}`
          : "同步请求失败，请确认本地 API 已启动后刷新页面重试。";
        if (!silent) toast.error(finalMsg);
        return {
          platform, kind: "failed", success: false, verified: false,
          safeErrorCode: code || (status === 409 ? "conflict" : "sync_request_failed"),
          safeMessage: msg || "同步请求失败，请确认本地 API 已启动",
          ...(status === 409 && code === "search_in_progress"
            ? { blockQueue: "search_in_progress" as const } : {}),
        };
      } finally {
        // Phase 5.1: 同步完成（成功/失败/后台验证中）后立即刷新账号缓存。
        invalidateAccounts(queryClient);
      }
    },
    [extensionState, queryClient]
  );

  // ── 重新验证 ─────────────────────────────────────────────────────────
  const verifyAccount = useCallback(async (platform: string) => {
    setBusyPlatform(platform, "verifying");
    try {
      await axios.post(`${API_BASE}/${platform}/verify`);
      setTimeout(() => setBusyPlatform(platform, ""), 2000);
    } catch (e) {
      setBusyPlatform(platform, "");
      const resp = (e as { response?: { status?: number; data?: { safe_message?: string; detail?: string } } }).response;
      const msg = resp?.data?.safe_message || resp?.data?.detail;
      toast.error(msg
        ? `验证请求失败：${msg}`
        : "验证请求失败，请确认本地 API 已启动后刷新页面重试。");
    } finally {
      // Phase 5.1: 验证完成（含后台验证进行中）后立即刷新账号缓存。
      invalidateAccounts(queryClient);
    }
  }, [queryClient]);

  // ── 清除登录状态（二次确认；破坏性操作保留原生 confirm 双重确认） ──
  const deleteSession = useCallback(async (platform: string) => {
    const name = PLATFORM_LABELS[platform as keyof typeof PLATFORM_LABELS] || platform;
    if (!window.confirm(`确定清除 ${name} 的登录状态吗？\n\n此操作会删除本地后台登录会话，之后需要重新同步。此操作不可撤销。`)) {
      return;
    }
    if (!window.confirm(`再次确认：将删除 ${name} 的后台登录数据（仅本地 browser_data 目录内），确定继续？`)) {
      return;
    }
    setBusyPlatform(platform, "deleting");
    try {
      await axios.delete(`${API_BASE}/${platform}/session`);
      toast.success(`已清除 ${name} 的登录状态。`);
    } catch (e) {
      const resp = (e as { response?: { status?: number; data?: { safe_message?: string; detail?: string } } }).response;
      const msg = resp?.data?.safe_message || resp?.data?.detail;
      toast.error(msg ? `清除失败：${msg}` : "清除失败，请确认本地 API 已启动。");
    } finally {
      setBusyPlatform(platform, "");
      // Phase 5.1: 删除完成后立即刷新账号缓存。
      invalidateAccounts(queryClient);
    }
  }, [queryClient]);

  // ── 一键同步四个平台（Round 14.3 / Phase 4.3）────────────────────────
  // 固定顺序 xhs → douyin → bilibili → zhihu，最大并发 2（生产模块
  // runBulkSync 编排）；复用 syncAccount（silent=true，不弹单平台 toast）。
  const [bulkSyncing, setBulkSyncing] = useState(false);
  const [bulkActive, setBulkActive] = useState<PlatformSlug[]>([]);
  const [bulkCompleted, setBulkCompleted] = useState(0);
  // 双击 guard：同步 ref（不能只依赖异步 React state）。
  const bulkGuardRef = useRef<ReturnType<typeof createBulkSyncGuard> | null>(null);
  if (bulkGuardRef.current === null) bulkGuardRef.current = createBulkSyncGuard();

  const handleBulkSync = useCallback(async () => {
    const guard = bulkGuardRef.current;
    if (!guard || !guard.tryStart()) return; // 双击 guard：拒绝第二套队列
    // 明确全局阻断（扩展未连接/过旧、API 不可用）→ 不启动队列，直接提示。
    const immediateBlock: BulkSyncBlockReason | null =
      extensionState === "outdated"
        ? "extension_outdated"
        : extensionState !== "connected"
          ? "extension_not_connected"
          : apiRunning === false
            ? "api_unavailable"
            : null;
    if (immediateBlock) {
      toast.warning(buildBulkBlockedMessage(immediateBlock));
      guard.finish();
      return;
    }
    setBulkSyncing(true);
    setBulkActive([]);
    setBulkCompleted(0);
    try {
      const result = await runBulkSync({
        syncOne: (platform) => syncAccount(platform, { silent: true }),
        checkBlock: () => (
          extensionState !== "connected"
            ? (extensionState === "outdated" ? "extension_outdated" : "extension_not_connected")
            : apiRunning === false
              ? "api_unavailable"
              : null
        ),
        onProgress: (p) => {
          setBulkActive(p.activePlatforms);
          setBulkCompleted(p.completedCount);
        },
      });
      // 汇总：全局阻断 → 一条总体提示；否则 → 一条汇总 toast。
      if (result.blocked && result.blockReason) {
        toast.warning(buildBulkBlockedMessage(result.blockReason));
      } else {
        const summary = buildBulkSummaryMessage(summarizeBulkOutcomes(result.outcomes));
        if (summary.tone === "success") {
          toast.success(summary.title);
        } else if (summary.tone === "warning") {
          toast.warning(summary.title, { description: summary.description });
        } else {
          toast.info(summary.title);
        }
      }
    } finally {
      setBulkSyncing(false);
      setBulkActive([]);
      guard.finish();
    }
  }, [extensionState, apiRunning, syncAccount]);

  // ── 备用辅助登录（默认折叠，仅用户主动点击）──────────────────────────
  const startAuxLogin = useCallback(async (platform: string) => {
    setAuxPlatform(platform);
    setAuxStatus({ job_id: "", platform, status: "pending", message: "正在启动独立辅助浏览器…" });
    try {
      const { data } = await axios.post("/api/search/login", { platform });
      setAuxStatus(data as LoginStatus);
    } catch (e) {
      setAuxStatus({ job_id: "", platform, status: "failed", message: "启动失败（可能有搜索正在运行）" });
    }
  }, []);

  useEffect(() => {
    if (!auxPlatform || !auxStatus?.job_id) return;
    const id = setInterval(async () => {
      try {
        const { data } = await axios.get(`/api/search/login/${auxStatus.job_id}`);
        setAuxStatus(data as LoginStatus);
        if (["succeeded", "failed", "timed_out"].includes(data.status)) {
          clearInterval(id);
        }
      } catch { clearInterval(id); }
    }, 1500);
    return () => clearInterval(id);
  }, [auxPlatform, auxStatus?.job_id]);

  const toggleDiag = (platform: string) => {
    setOpenDiag((prev) => ({ ...prev, [platform]: !prev[platform] }));
  };

  // ── 渲染 ─────────────────────────────────────────────────────────────
  return (
    <div className="pt-7 pb-4">
      <div className="mb-6">
        <h1 className="text-[22px] font-bold text-cyber-text-primary">设置</h1>
        <p className="mt-1 text-[13.5px] text-cyber-text-muted">
          统一管理搜索数量与本地账号登录状态
        </p>
      </div>

      {/* ── 搜索设置（Round 15） ── */}
      <section className="mb-8">
        <h2 className="text-[16px] font-bold text-cyber-text-primary mb-1">搜索设置</h2>
        <p className="text-[12.5px] text-cyber-text-muted mb-3.5">
          数量越大，搜索耗时可能越长，也更容易遇到平台请求限制。修改后从下一次搜索开始生效。
        </p>
        <div className="flex flex-col gap-2.5">
          {PLATFORM_ORDER.map((p) => (
            <LimitRow
              key={p}
              platform={p}
              value={limits[p]}
              onChange={(v) => setLimit(p, v)}
            />
          ))}
        </div>
        <button
          type="button"
          onClick={resetAll}
          className="mt-3 px-3.5 py-2 rounded-[10px] border border-cyber-border-subtle text-xs text-cyber-text-secondary hover:bg-cyber-bg-tertiary hover:text-cyber-text-primary transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5 inline mr-1.5" />恢复默认
        </button>
      </section>

      {/* ── 账号与登录 ── */}
      <section>
        <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
          <h2 className="text-[16px] font-bold text-cyber-text-primary">账号与登录</h2>
          {/* 一键同步四平台：并发 2，固定顺序 xhs → douyin → bilibili → zhihu */}
          <button
            type="button"
            onClick={handleBulkSync}
            disabled={bulkSyncing || extensionState !== "connected" || apiRunning === false}
            className="w-full sm:w-auto flex items-center justify-center gap-2 px-4 py-2.5 rounded-[12px] bg-brand text-white font-semibold text-[13.5px] shadow-[0_8px_22px_rgba(76,164,220,0.25)] hover:bg-brand-strong transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {bulkSyncing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                {bulkActive.length > 0
                  ? `正在同步：${bulkActive.map((p) => PLATFORM_LABELS[p]).join("、")} · ${Math.min(bulkCompleted + bulkActive.length, 4)}/4`
                  : `${bulkCompleted}/4`}
              </>
            ) : (
              <>
                <RefreshCw className="w-4 h-4" />
                一键同步四个平台
              </>
            )}
          </button>
        </div>

      {/* 扩展状态 */}
      <div className={`mb-5 px-4 py-2.5 rounded-xl border text-[12.5px] w-fit ${
        extensionState === "connected"
          ? "border-ok/40 bg-ok-soft text-[#3d7d60]"
          : extensionState === "outdated" || extensionState === "not-installed"
            ? "border-warn/40 bg-warn-soft text-warn"
            : "border-cyber-border-subtle bg-cyber-bg-secondary text-cyber-text-muted"
      }`}>
        <Plug className="w-3.5 h-3.5 inline mr-1.5" />
        {extensionState === "checking" && "正在检测浏览器扩展…"}
        {extensionState === "connected"
          && `扩展已安装并连接（v${extensionVersion || "?"}，协议 v2）`}
        {extensionState === "outdated"
          && `扩展版本过旧${extensionVersion ? `（检测到 v${extensionVersion}）` : ""}，请在 edge://extensions 点击"重新加载"后刷新本页`}
        {extensionState === "not-installed" && "未检测到扩展（安装后需刷新本页）"}
        {apiRunning === false && " · 本地 API 未运行"}
      </div>

      {/* 平台卡片：统一浅色账号卡 */}
      <div className="flex flex-col gap-3">
        {(accounts || []).map((acc) => {
          const busyLabel = busy[acc.platform];
          const name = PLATFORM_LABELS[acc.platform as keyof typeof PLATFORM_LABELS] || acc.platform;
          const color = PLATFORM_COLORS[acc.platform as keyof typeof PLATFORM_COLORS] || "#4ca4dc";
          const tone = accountTone(acc);
          const hasDiag = !!lastDiag[acc.platform];
          return (
            <div key={acc.platform} className="rounded-[16px] border border-cyber-border-subtle bg-cyber-bg-secondary p-4 sm:p-5">
              {/* 头部：平台标记 + 名称 + 状态徽章 + busy */}
              <div className="flex items-center justify-between gap-3 mb-3.5 flex-wrap">
                <div className="flex items-center gap-3">
                  <span
                    className="w-[38px] h-[38px] rounded-[11px] grid place-items-center text-[15px] font-extrabold text-white flex-shrink-0"
                    style={{ backgroundColor: color }}
                  >
                    {PLATFORM_LETTERS[acc.platform]}
                  </span>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-[14.5px] font-bold text-cyber-text-primary">{name}</span>
                      <span className={`px-2 py-0.5 rounded-full text-[10.5px] border ${TONE_BADGE[tone]}`}>
                        {accountStatusText(acc)}
                        {acc.verified && <ShieldCheck className="w-3 h-3 inline ml-1" />}
                      </span>
                    </div>
                  </div>
                </div>
                {busyLabel && (
                  <span className="flex items-center gap-1.5 text-xs text-brand-strong">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    {busyLabel === "syncing" && "同步中…"}
                    {busyLabel === "verifying" && "验证中…"}
                    {busyLabel === "deleting" && "清除中…"}
                  </span>
                )}
              </div>

              {/* 概要信息 */}
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12.5px] text-cyber-text-secondary mb-3">
                <div>后台会话：{acc.profile_exists ? "已存在" : "不存在"}</div>
                <div>浏览器后端：{acc.browser_backend ? (BACKEND_TEXT[acc.browser_backend] || acc.browser_backend) : "—"}</div>
                <div>昵称：{acc.display_name || "—"}</div>
                <div>上次验证：{acc.last_verified_at ? new Date(acc.last_verified_at).toLocaleString("zh-CN") : "—"}</div>
              </div>

              {acc.safe_message && (
                <div className="mb-3 px-3.5 py-2 rounded-lg bg-warn-soft border border-warn/30 text-xs text-warn">
                  {acc.safe_message}
                </div>
              )}

              {/* 诊断信息：默认折叠 */}
              {hasDiag && (
                <div className="mb-3">
                  <button
                    type="button"
                    onClick={() => toggleDiag(acc.platform)}
                    className="flex items-center gap-1 text-[11.5px] text-cyber-text-muted hover:text-brand-strong transition-colors"
                  >
                    {openDiag[acc.platform] ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                    {openDiag[acc.platform] ? "收起诊断" : "查看诊断"}
                  </button>
                  {openDiag[acc.platform] && (
                    <div className="mt-2 px-3.5 py-2.5 rounded-lg bg-cyber-bg-tertiary border border-cyber-border-subtle text-[11px] text-cyber-text-secondary">
                      <div className="text-cyber-text-primary mb-1 font-semibold">最近一次同步诊断</div>
                      <div>
                        阶段：{SYNC_STAGE_TEXT[lastDiag[acc.platform].sync_stage] || lastDiag[acc.platform].sync_stage || "—"}
                        {" · "}读取 {lastDiag[acc.platform].received_cookie_count ?? "—"} 条
                        {" / 接受 "}{lastDiag[acc.platform].accepted_cookie_count ?? "—"} 条
                        {" / 跳过 "}{lastDiag[acc.platform].skipped_cookie_count ?? "—"} 条
                      </div>
                      <div>
                        登录标记：
                        {(LOGIN_MARKERS[acc.platform] || []).map((m) => {
                          const v = lastDiag[acc.platform].login_marker_presence?.[m];
                          return v === undefined ? null : `${m} ${v ? "✓" : "✗"}`;
                        }).filter(Boolean).join(" · ") || "—"}
                      </div>
                      <div>
                        标记判定（启发式，非登录结论）：{lastDiag[acc.platform].required_cookie_present === null
                          ? "—" : lastDiag[acc.platform].required_cookie_present ? "有" : "无"}
                        {" · 已验证（真实验证）："}{lastDiag[acc.platform].verified ? "是" : "否"}
                      </div>
                      {lastDiag[acc.platform].safe_error_code && (
                        <div>
                          错误码：{lastDiag[acc.platform].safe_error_code}
                          {lastDiag[acc.platform].safe_message && ` · ${lastDiag[acc.platform].safe_message}`}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* 主要操作 */}
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => openOfficial(acc.platform)}
                  className="px-3.5 py-2 rounded-[10px] border border-cyber-border-subtle text-xs text-cyber-text-primary hover:bg-cyber-bg-tertiary transition-colors"
                >
                  <ExternalLink className="w-3.5 h-3.5 inline mr-1.5" />打开官网
                </button>
                <button
                  onClick={() => syncAccount(acc.platform as PlatformSlug)}
                  disabled={!!busyLabel || extensionState !== "connected" || bulkSyncing}
                  className="px-3.5 py-2 rounded-[10px] bg-brand-soft border border-brand/40 text-brand-strong hover:bg-brand/10 text-xs font-semibold transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  同步当前浏览器登录状态
                </button>
                <button
                  onClick={() => verifyAccount(acc.platform)}
                  disabled={!!busyLabel || bulkSyncing}
                  className="px-3.5 py-2 rounded-[10px] border border-cyber-border-subtle text-xs text-cyber-text-primary hover:bg-cyber-bg-tertiary transition-colors disabled:opacity-40"
                >
                  <RefreshCw className="w-3.5 h-3.5 inline mr-1.5" />重新验证
                </button>
                <button
                  onClick={() => deleteSession(acc.platform)}
                  disabled={!!busyLabel || !acc.profile_exists || bulkSyncing}
                  className="px-3.5 py-2 rounded-[10px] border border-danger/40 text-danger hover:bg-danger-soft text-xs transition-colors disabled:opacity-40"
                >
                  <Trash2 className="w-3.5 h-3.5 inline mr-1.5" />清除登录状态
                </button>
              </div>

              {/* 备用辅助登录（折叠） */}
              <div className="mt-3">
                <button
                  onClick={() => { setAuxOpen(!auxOpen); setAuxPlatform(null); setAuxStatus(null); }}
                  className="text-[11.5px] text-cyber-text-muted hover:text-cyber-text-primary underline underline-offset-2 transition-colors"
                >
                  {auxOpen ? "收起" : "备用辅助登录"}（扩展同步失败时使用）
                </button>
                {auxOpen && (
                  <div className="mt-2 px-3.5 py-2.5 rounded-lg border border-cyber-border-subtle bg-cyber-bg-tertiary/60">
                    <p className="text-[11.5px] text-warn mb-2">
                      ⚠ 将打开独立辅助浏览器窗口进行扫码登录（不会复用当前浏览器会话）。
                    </p>
                    <div className="flex items-center gap-2 flex-wrap">
                      <button
                        onClick={() => startAuxLogin(acc.platform)}
                        disabled={!!auxStatus && ["pending", "running"].includes(auxStatus.status)}
                        className="px-3 py-1.5 rounded-lg bg-warn-soft border border-warn/40 text-warn text-xs hover:bg-warn/10 transition-all disabled:opacity-40"
                      >
                        {auxStatus && auxStatus.status === "running" ? <Loader2 className="w-3 h-3 animate-spin inline mr-1" /> : null}
                        打开辅助登录窗口
                      </button>
                      {auxStatus && auxStatus.message && (
                        <span className="text-[11.5px] text-cyber-text-muted">{auxStatus.message}</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 安装说明 */}
      <div className="mt-6 p-4 sm:p-5 rounded-[16px] border border-cyber-border-subtle bg-cyber-bg-secondary text-xs text-cyber-text-muted">
        <p className="text-cyber-text-primary mb-2 font-bold text-[13.5px]">安装浏览器扩展</p>
        <ol className="list-decimal list-inside space-y-1">
          <li>打开 <code className="text-brand-strong">chrome://extensions</code>（Edge 为 <code className="text-brand-strong">edge://extensions</code>）；</li>
          <li>开启右上角<b>开发者模式</b>；</li>
          <li>点击<b>加载已解压的扩展程序</b>；</li>
          <li>选择项目目录下的 <code className="text-brand-strong">browser_extension</code> 文件夹；</li>
          <li>刷新本页（扩展注入后需刷新一次才能检测到）。</li>
        </ol>
        <p className="mt-2 text-cyber-text-muted">
          安全说明：扩展只读取四个平台官方域名的登录 Cookie，直接发送到本机 127.0.0.1:8080 后端；
          网页只能收到同步结果状态，拿不到任何 Cookie。本系统不保存平台用户名或密码。
        </p>
      </div>
      </section>

      {onNavigateSearch && (
        <button
          onClick={onNavigateSearch}
          className="mt-4 text-xs text-cyber-text-muted hover:text-brand-strong underline underline-offset-2 transition-colors"
        >
          ← 返回聚合搜索
        </button>
      )}
    </div>
  );
}
