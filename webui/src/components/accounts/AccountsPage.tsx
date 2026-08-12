import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { Loader2, RefreshCw, Trash2, ExternalLink, Plug, ShieldCheck } from "lucide-react";
import { PLATFORM_LABELS, PLATFORM_ICONS } from "@/types/search";

interface AccountInfo {
  platform: string;
  profile_exists: boolean;
  status: string;
  verified: boolean;
  display_name: string | null;
  last_verified_at: string | null;
  safe_error_code: string | null;
  safe_message: string | null;
  browser_backend: string | null;
}

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

interface AccountsPageProps {
  onNavigateSearch?: () => void;
}

export function AccountsPage({ onNavigateSearch }: AccountsPageProps) {
  const [accounts, setAccounts] = useState<AccountInfo[] | null>(null);
  const [apiRunning, setApiRunning] = useState<boolean | null>(null);
  const [extensionState, setExtensionState] = useState<
    "checking" | "connected" | "outdated" | "not-installed" | "unknown"
  >("checking");
  const [busy, setBusy] = useState<Record<string, string>>({});
  const [lastDiag, setLastDiag] = useState<Record<string, SyncResult>>({});
  const [auxOpen, setAuxOpen] = useState(false);
  const [auxPlatform, setAuxPlatform] = useState<string | null>(null);
  const [auxStatus, setAuxStatus] = useState<LoginStatus | null>(null);
  const extPong = useRef(false);
  const [extensionVersion, setExtensionVersion] = useState("");

  // ── API 运行检测 ─────────────────────────────────────────────────────
  useEffect(() => {
    let alive = true;
    fetch("/api/health")
      .then((r) => r.json())
      .then((d) => alive && setApiRunning(d?.status === "ok"))
      .catch(() => alive && setApiRunning(false));
    return () => { alive = false; };
  }, []);

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

  // ── 账号列表轮询（同步/验证期间加速）────────────────────────────────
  useEffect(() => {
    if (apiRunning !== true) return;
    let alive = true;
    const fetchAccounts = async () => {
      try {
        const { data } = await axios.get(API_BASE);
        if (alive) setAccounts(data.accounts);
      } catch { /* 保持上次状态 */ }
    };
    fetchAccounts();
    const id = setInterval(fetchAccounts, 3000);
    return () => { alive = false; clearInterval(id); };
  }, [apiRunning]);

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

  // ── 同步当前浏览器登录状态 ───────────────────────────────────────────
  const syncAccount = useCallback(async (platform: string) => {
    if (extensionState === "not-installed") {
      alert("未检测到浏览器扩展，请先安装（见页面底部安装说明）后刷新本页。");
      return;
    }
    if (extensionState === "outdated") {
      // 禁止继续同步：旧脚本（1.1.2 及更早）协议同为 v2，但可能缺少
      // 后端需要的字段，继续同步会得到不可靠的诊断结果。
      alert("扩展版本过旧，请在 edge://extensions 点击\"重新加载\"后刷新本页再同步。");
      return;
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
        alert(`扩展 ${Math.round(SYNC_RESPONSE_TIMEOUT_MS / 1000)} 秒未响应。`
          + "请确认：1) 扩展已加载并启用；2) 已刷新本页（扩展注入后需刷新一次）；"
          + "3) 后端验证会话最长约 30 秒，若仍在验证可稍等后查看账号卡片诊断。");
        return;
      }
      setLastDiag((prev) => ({ ...prev, [platform]: result }));
      // 同步不成功：显示后端/扩展返回的安全错误（可能是 Cookie 未读取到、
      // 格式不兼容、会话导入失败或正在搜索不能同步等）。
      if (!result.success) {
        setBusyPlatform(platform, "");
        const counts = typeof result.received_cookie_count === "number"
          ? `（读取 ${result.received_cookie_count} 条）` : "";
        alert(`同步失败${counts}：${result.safe_message || result.safe_error_code || "未知错误"}`);
        return;
      }
      // Round 11：success alert 只允许在真实验证通过时显示 ——
      // status==="connected" && verified===true && 无安全错误码。
      // （unavailable 等场景绝不显示"同步成功且登录验证通过"。）
      if (result.verified && result.status === "connected" && !result.safe_error_code) {
        setBusyPlatform(platform, "");
        const counts = typeof result.received_cookie_count === "number"
          ? `（读取 ${result.received_cookie_count} 条 / 接受 ${result.accepted_cookie_count ?? "?"} 条）` : "";
        alert(`同步成功且登录验证通过。${counts}`);
        return;
      }
      const importedCounts = typeof result.received_cookie_count === "number"
        ? `（读取 ${result.received_cookie_count} 条 / 接受 ${result.accepted_cookie_count ?? "?"} 条）` : "";
      // 有界验证超时，验证仍在后台进行：busy 保持 "verifying"，直到账号
      // 轮询看到终态（见上面的 busy 清理 effect）。
      if (result.status === "verifying") {
        setBusyPlatform(platform, "verifying");
        alert(`会话已导入，仍在后台验证 ${importedCounts}。可在本卡片查看诊断，或稍后点击"重新验证"确认结果。`);
        return;
      }
      // Round 11：验证暂不可用（网络/超时/403 风控/导航失败）必须优先
      // 显示后端 safe_message，绝不落入下方"尚未确认账号登录"的提示
      // （那会错误地声称明确未登录）。
      if (result.status === "unavailable" || result.safe_error_code === "login_verification_unavailable") {
        setBusyPlatform(platform, "");
        alert(result.safe_message || "当前无法验证登录状态，仍可尝试搜索或稍后重新验证");
        return;
      }
      // 明确未登录（expired / unverified）：已导入但未确认登录，这不是
      // 失败 —— 公开搜索仍可尝试。
      setBusyPlatform(platform, "");
      alert(`会话已导入，但尚未确认账号登录。你仍可以尝试搜索；如搜索需要登录，再重新同步。${importedCounts}`);
    } catch (e) {
      setBusyPlatform(platform, "");
      // 解析后端结构化错误（safe_message / detail），而不是统一显示"API 可能未启动"
      const resp = (e as { response?: { status?: number; data?: { safe_message?: string; detail?: string } } }).response;
      const msg = resp?.data?.safe_message || resp?.data?.detail;
      alert(msg
        ? `同步请求失败：${msg}`
        : "同步请求失败，请确认本地 API 已启动后刷新页面重试。");
    }
  }, [extensionState]);

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
      alert(msg
        ? `验证请求失败：${msg}`
        : "验证请求失败，请确认本地 API 已启动后刷新页面重试。");
    }
  }, []);

  // ── 清除登录状态（二次确认）──────────────────────────────────────────
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
    } catch (e) {
      const resp = (e as { response?: { status?: number; data?: { safe_message?: string; detail?: string } } }).response;
      const msg = resp?.data?.safe_message || resp?.data?.detail;
      alert(msg ? `清除失败：${msg}` : "清除失败，请确认本地 API 已启动。");
    } finally {
      setBusyPlatform(platform, "");
    }
  }, []);

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

  // ── 渲染 ─────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col items-center px-4 py-6 h-full overflow-y-auto">
      <div className="text-center mb-6">
        <h1 className="text-2xl font-mono font-bold text-cyber-text-primary">账号设置</h1>
        <p className="mt-2 text-sm font-mono text-cyber-text-muted">
          在浏览器官方站点登录后，把登录会话同步到本地后台供无头搜索使用
        </p>
      </div>

      {/* 扩展状态 */}
      <div className={`mb-4 px-4 py-2 rounded-lg border text-xs font-mono ${
        extensionState === "connected"
          ? "border-cyber-neon-green/50 bg-cyber-neon-green/10 text-cyber-neon-green"
          : extensionState === "outdated" || extensionState === "not-installed"
            ? "border-cyber-neon-orange/50 bg-cyber-neon-orange/10 text-cyber-neon-orange"
            : "border-cyber-border-subtle bg-cyber-bg-tertiary text-cyber-text-muted"
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

      {/* 平台卡片 */}
      <div className="w-full max-w-3xl space-y-3">
        {(accounts || []).map((acc) => {
          const busyLabel = busy[acc.platform];
          const name = PLATFORM_LABELS[acc.platform as keyof typeof PLATFORM_LABELS] || acc.platform;
          return (
            <div key={acc.platform} className="rounded-lg border border-cyber-border-subtle bg-cyber-bg-tertiary/60 p-4">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{PLATFORM_ICONS[acc.platform as keyof typeof PLATFORM_ICONS]}</span>
                  <span className="font-mono text-sm font-bold text-cyber-text-primary">{name}</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-mono ${
                    acc.verified
                      ? "bg-cyber-neon-green/10 text-cyber-neon-green border border-cyber-neon-green/40"
                      : acc.status === "expired" || acc.status === "failed"
                        ? "bg-cyber-neon-pink/10 text-cyber-neon-pink border border-cyber-neon-pink/40"
                        : "bg-cyber-bg-secondary text-cyber-text-muted border border-cyber-border-subtle"
                  }`}>
                    {STATUS_TEXT[acc.status] || acc.status}
                    {acc.verified && <ShieldCheck className="w-3 h-3 inline ml-1" />}
                  </span>
                </div>
                {busyLabel && (
                  <span className="flex items-center gap-1 text-xs font-mono text-cyber-neon-cyan">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    {busyLabel === "syncing" && "同步中…"}
                    {busyLabel === "verifying" && "验证中…"}
                    {busyLabel === "deleting" && "清除中…"}
                  </span>
                )}
              </div>

              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-mono text-cyber-text-muted mb-3">
                <div>后台会话：{acc.profile_exists ? "已存在" : "不存在"}</div>
                <div>浏览器后端：{acc.browser_backend ? (BACKEND_TEXT[acc.browser_backend] || acc.browser_backend) : "—"}</div>
                <div>昵称：{acc.display_name || "—"}</div>
                <div>上次验证：{acc.last_verified_at ? new Date(acc.last_verified_at).toLocaleString("zh-CN") : "—"}</div>
              </div>

              {acc.safe_message && (
                <div className="mb-3 px-3 py-1.5 rounded bg-cyber-neon-orange/5 border border-cyber-neon-orange/30 text-xs font-mono text-cyber-neon-orange">
                  {acc.safe_message}
                </div>
              )}

              {lastDiag[acc.platform] && (
                <div className="mb-3 px-3 py-2 rounded bg-cyber-bg-secondary border border-cyber-border-subtle text-[11px] font-mono text-cyber-text-muted">
                  <div className="text-cyber-text-primary mb-1">最近一次同步诊断</div>
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

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => openOfficial(acc.platform)}
                  className="px-3 py-1.5 rounded-lg border border-cyber-border-subtle text-xs font-mono text-cyber-text-primary hover:bg-cyber-bg-secondary transition-all"
                >
                  <ExternalLink className="w-3 h-3 inline mr-1" />打开官方登录页
                </button>
                <button
                  onClick={() => syncAccount(acc.platform)}
                  disabled={!!busyLabel || extensionState !== "connected"}
                  className="px-3 py-1.5 rounded-lg bg-cyber-neon-cyan/10 border border-cyber-neon-cyan/50 text-cyber-neon-cyan hover:bg-cyber-neon-cyan/20 text-xs font-mono transition-all disabled:opacity-40"
                >
                  同步当前浏览器登录状态
                </button>
                <button
                  onClick={() => verifyAccount(acc.platform)}
                  disabled={!!busyLabel}
                  className="px-3 py-1.5 rounded-lg border border-cyber-border-subtle text-xs font-mono text-cyber-text-primary hover:bg-cyber-bg-secondary transition-all disabled:opacity-40"
                >
                  <RefreshCw className="w-3 h-3 inline mr-1" />重新验证
                </button>
                <button
                  onClick={() => deleteSession(acc.platform)}
                  disabled={!!busyLabel || !acc.profile_exists}
                  className="px-3 py-1.5 rounded-lg border border-cyber-neon-pink/40 text-cyber-neon-pink hover:bg-cyber-neon-pink/10 text-xs font-mono transition-all disabled:opacity-40"
                >
                  <Trash2 className="w-3 h-3 inline mr-1" />清除登录状态
                </button>
              </div>

              <div className="mt-2">
                <button
                  onClick={() => { setAuxOpen(!auxOpen); setAuxPlatform(null); setAuxStatus(null); }}
                  className="text-[11px] font-mono text-cyber-text-muted hover:text-cyber-text-primary underline underline-offset-2"
                >
                  {auxOpen ? "收起" : "备用辅助登录"}（扩展同步失败时使用）
                </button>
                {auxOpen && (
                  <div className="mt-2 px-3 py-2 rounded border border-cyber-border-subtle bg-cyber-bg-secondary/50">
                    <p className="text-[11px] font-mono text-cyber-neon-orange mb-2">
                      ⚠ 将打开独立辅助浏览器窗口进行扫码登录（不会复用当前浏览器会话）。
                    </p>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => startAuxLogin(acc.platform)}
                        disabled={!!auxStatus && ["pending", "running"].includes(auxStatus.status)}
                        className="px-3 py-1 rounded bg-cyber-neon-orange/10 border border-cyber-neon-orange/40 text-cyber-neon-orange text-xs font-mono hover:bg-cyber-neon-orange/20 transition-all disabled:opacity-40"
                      >
                        {auxStatus && auxStatus.status === "running" ? <Loader2 className="w-3 h-3 animate-spin inline mr-1" /> : null}
                        打开辅助登录窗口
                      </button>
                      {auxStatus && auxStatus.message && (
                        <span className="text-[11px] font-mono text-cyber-text-muted">{auxStatus.message}</span>
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
      <div className="w-full max-w-3xl mt-6 p-4 rounded-lg border border-cyber-border-subtle bg-cyber-bg-tertiary/40 text-xs font-mono text-cyber-text-muted">
        <p className="text-cyber-text-primary mb-2 font-bold">安装浏览器扩展</p>
        <ol className="list-decimal list-inside space-y-1">
          <li>打开 <code className="text-cyber-neon-cyan">chrome://extensions</code>（Edge 为 <code className="text-cyber-neon-cyan">edge://extensions</code>）；</li>
          <li>开启右上角<b>开发者模式</b>；</li>
          <li>点击<b>加载已解压的扩展程序</b>；</li>
          <li>选择项目目录下的 <code className="text-cyber-neon-cyan">browser_extension</code> 文件夹；</li>
          <li>刷新本页（扩展注入后需刷新一次才能检测到）。</li>
        </ol>
        <p className="mt-2 text-cyber-text-muted">
          安全说明：扩展只读取四个平台官方域名的登录 Cookie，直接发送到本机 127.0.0.1:8080 后端；
          网页只能收到同步结果状态，拿不到任何 Cookie。本系统不保存平台用户名或密码。
        </p>
      </div>

      {onNavigateSearch && (
        <button
          onClick={onNavigateSearch}
          className="mt-4 text-xs font-mono text-cyber-text-muted hover:text-cyber-neon-cyan underline underline-offset-2 transition-colors"
        >
          ← 返回聚合搜索
        </button>
      )}
    </div>
  );
}
