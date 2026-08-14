/**
 * Phase 5.1 账号共享查询测试 —— 直接 import 生产模块
 * （webui/src/hooks/useAccounts.ts）的纯 helper，不复制任何生产逻辑。
 *
 * 真实"只有一个 HTTP 请求"由浏览器人工验证（Node 无 DOM 网络测试基建）；
 * 这里用确定性断言覆盖 query key、轮询决策与 invalidation 接线。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  ACCOUNTS_QUERY_KEY,
  HEALTH_QUERY_KEY,
  accountsQueryOptions,
  accountsRefetchInterval,
  invalidateAccounts,
} from "../src/hooks/useAccounts.js";
import type { QueryClient } from "@tanstack/react-query";

test("query keys 固定：accounts 与 api-health", () => {
  assert.deepEqual([...ACCOUNTS_QUERY_KEY], ["accounts"]);
  assert.deepEqual([...HEALTH_QUERY_KEY], ["api-health"]);
});

test("轮询间隔决策：前台 3s，后台停止（不占高频请求）", () => {
  assert.equal(accountsRefetchInterval(true), 3000);
  assert.equal(accountsRefetchInterval(false), false);
});

test("accountsQueryOptions：queryKey 固定、enabled 透传、stale 保留旧数据", () => {
  const opts = accountsQueryOptions(true) as {
    queryKey: readonly string[];
    enabled: boolean;
    staleTime: number;
    retry: number;
    refetchInterval: () => number | false;
  };
  assert.deepEqual(opts.queryKey, ["accounts"]);
  assert.equal(opts.enabled, true);
  assert.equal(accountsQueryOptions(false).enabled, false);
  assert.equal(opts.staleTime, 500); // 偶发失败保留旧数据（stale）
  assert.equal(opts.retry, 1);
  // 轮询间隔走纯函数决策。
  assert.equal(typeof opts.refetchInterval, "function");
});

test("invalidateAccounts 使用固定 queryKey 触发失效", () => {
  let captured: unknown = null;
  const fake = {
    invalidateQueries: (opts: unknown) => {
      captured = opts;
    },
  } as unknown as QueryClient;
  invalidateAccounts(fake);
  assert.deepEqual(captured, { queryKey: ["accounts"] });
});
