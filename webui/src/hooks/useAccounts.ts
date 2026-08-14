/**
 * 账号列表共享 hook（Round 14 / Phase 5.1，基于 TanStack Query）。
 *
 * 供顶部栏登录状态浮层与账号设置页共用 —— 同一固定 queryKey，Header 与
 * AccountsPage 同时挂载时共享缓存与轮询，不各发一套 3 秒请求：
 * - 仍走 GET /api/health 与 GET /api/search/accounts；
 * - 仍只在 apiRunning === true 时轮询；
 * - 返回契约不变：accounts / loading / initialLoaded / error / apiRunning；
 * - 偶发刷新失败保留旧数据（stale），不把旧账号瞬间清空；
 * - 页面后台时停止高频轮询（纯函数 accountsRefetchInterval 决策）；
 * - sync/verify/delete 完成后调用 invalidateAccounts 立即刷新。
 *
 * 不新建第二个 QueryClient：使用应用已安装的 TanStack Query。
 */

import { useQuery } from "@tanstack/react-query";
import type { QueryClient } from "@tanstack/react-query";
import axios from "axios";
import type { AccountStatusInfo } from "@/lib/accounts";

const API_BASE = "/api/search/accounts";
const POLL_INTERVAL_MS = 3000;

export const ACCOUNTS_QUERY_KEY = ["accounts"] as const;
export const HEALTH_QUERY_KEY = ["api-health"] as const;

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

/** 轮询间隔决策（纯函数）：后台页返回 false（停止轮询），否则固定 3s。 */
export function accountsRefetchInterval(pageVisible: boolean): number | false {
  return pageVisible ? POLL_INTERVAL_MS : false;
}

function _pageVisible(): boolean {
  if (typeof document === "undefined") return true;
  return document.visibilityState !== "hidden";
}

/** 账号列表查询选项（纯对象，供测试验证 key/enabled/interval）。 */
export function accountsQueryOptions(enabled: boolean) {
  return {
    queryKey: ACCOUNTS_QUERY_KEY,
    enabled,
    refetchInterval: () => accountsRefetchInterval(_pageVisible()),
    staleTime: 500,
    retry: 1,
  };
}

/** sync/verify/delete 完成后调用：立即刷新共享缓存，不必等下一次轮询。 */
export function invalidateAccounts(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: ACCOUNTS_QUERY_KEY });
}

export function useAccounts(): UseAccountsResult {
  const healthQuery = useQuery({
    queryKey: HEALTH_QUERY_KEY,
    queryFn: async () => {
      try {
        const r = await fetch("/api/health");
        const d = await r.json();
        return d?.status === "ok";
      } catch {
        return false;
      }
    },
    refetchInterval: () => accountsRefetchInterval(_pageVisible()),
    staleTime: 500,
    retry: 0,
  });

  const apiRunning: boolean | null = healthQuery.isPending
    ? null
    : healthQuery.data === true;

  const accountsQuery = useQuery({
    ...accountsQueryOptions(apiRunning === true),
    queryFn: async () => {
      const { data } = await axios.get(API_BASE);
      return data.accounts as AccountStatusInfo[];
    },
  });

  return {
    accounts: accountsQuery.data ?? null,
    loading: accountsQuery.isPending || healthQuery.isPending,
    initialLoaded: accountsQuery.data !== undefined,
    error: accountsQuery.isError || apiRunning === false,
    apiRunning,
  };
}
