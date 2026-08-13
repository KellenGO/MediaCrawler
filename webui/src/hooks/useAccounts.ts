/**
 * 账号列表共享 hook（Round 14 抽取，Round 14.2 增加加载/错误状态）。
 *
 * 供顶部栏登录状态浮层与账号设置页共用 —— 不复制业务逻辑、不改语义：
 * - 仍走 GET /api/health 与 GET /api/search/accounts；
 * - 仍只在 apiRunning === true 时轮询；
 * - 新增 loading / initialLoaded / error：UI 可区分"从未成功加载"与
 *   "曾经加载成功、当前一次刷新失败"（偶发失败保留旧数据）。
 */

import { useEffect, useState } from "react";
import axios from "axios";
import type { AccountStatusInfo } from "@/lib/accounts";

const API_BASE = "/api/search/accounts";
const POLL_INTERVAL_MS = 3000;

export interface UseAccountsResult {
  accounts: AccountStatusInfo[] | null;
  /** 首次加载进行中（健康检查或首次账号请求未决）。 */
  loading: boolean;
  /** 是否曾成功加载过账号列表。 */
  initialLoaded: boolean;
  /** 最近一次请求失败（曾成功加载时保留旧 accounts，由 UI 用 stale 区分）。 */
  error: boolean;
  apiRunning: boolean | null;
}

export function useAccounts(): UseAccountsResult {
  const [accounts, setAccounts] = useState<AccountStatusInfo[] | null>(null);
  const [apiRunning, setApiRunning] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [initialLoaded, setInitialLoaded] = useState(false);
  const [error, setError] = useState(false);

  // ── API 运行检测 ─────────────────────────────────────────────────────
  useEffect(() => {
    let alive = true;
    fetch("/api/health")
      .then((r) => r.json())
      .then((d) => alive && setApiRunning(d?.status === "ok"))
      .catch(() => alive && setApiRunning(false));
    return () => { alive = false; };
  }, []);

  // ── 账号列表轮询（同步/验证期间加速由账号卡片 busy 状态体现） ────────
  useEffect(() => {
    if (apiRunning === null) return; // 健康检查未完成：保持 loading（检查中）
    if (apiRunning !== true) {
      // 本地 API 不可用：首次请求不可能成功 → 标记失败（UI 显示"暂不可用"）
      setLoading(false);
      setError(true);
      return;
    }
    let alive = true;
    const fetchAccounts = async () => {
      try {
        const { data } = await axios.get(API_BASE);
        if (!alive) return;
        setAccounts(data.accounts as AccountStatusInfo[]);
        setInitialLoaded(true);
        setError(false);
      } catch {
        // 偶发失败：保留旧 accounts（initialLoaded 让 UI 区分新旧数据）
        if (!alive) return;
        setError(true);
      } finally {
        if (alive) setLoading(false);
      }
    };
    fetchAccounts();
    const id = setInterval(fetchAccounts, POLL_INTERVAL_MS);
    return () => { alive = false; clearInterval(id); };
  }, [apiRunning]);

  return { accounts, loading, initialLoaded, error, apiRunning };
}
