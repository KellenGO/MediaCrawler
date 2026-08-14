/**
 * 按平台独立搜索数量（Round 15，无 React 依赖）。
 *
 * 持久化到 localStorage（key: aggregate_search_platform_limits_v1），
 * 只存四个平台的数量，不存 Cookie/账号/搜索结果等其他数据。
 *
 * 规则：
 * - 每个平台 1–20，默认 10；
 * - 读取时按字段恢复：单个字段非法只丢弃该字段，其余合法字段保留；
 * - 未知平台被过滤；
 * - boolean/NaN/Infinity/空字符串/对象/数组不能当合法数字；
 * - 存储失败安全回退，不阻止搜索；
 * - 修改一个平台不影响其他平台（不可变更新，不 mutate 输入）。
 */

import type { PlatformSlug } from "../types/search.js";

export const PLATFORM_LIMITS_STORAGE_KEY = "aggregate_search_platform_limits_v1";
export const MIN_PLATFORM_LIMIT = 1;
export const MAX_PLATFORM_LIMIT = 20;
export const DEFAULT_PLATFORM_LIMIT = 10;

export type PlatformLimitMap = Record<PlatformSlug, number>;

export const PLATFORM_ORDER: readonly PlatformSlug[] = [
  "xhs",
  "douyin",
  "bilibili",
  "zhihu",
];

export const DEFAULT_PLATFORM_LIMITS: PlatformLimitMap = {
  xhs: DEFAULT_PLATFORM_LIMIT,
  douyin: DEFAULT_PLATFORM_LIMIT,
  bilibili: DEFAULT_PLATFORM_LIMIT,
  zhihu: DEFAULT_PLATFORM_LIMIT,
};

/** localStorage 的窄接口（测试可用内存实现）。 */
export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

/**
 * 归一化单个数量：
 * - 非 number / NaN / Infinity（含 boolean、字符串、null、对象、数组）→ null（非法）；
 * - 合法数字 → 四舍五入取整后夹紧到 [1, 20]（0→1、21→20、-5→1）。
 */
export function normalizePlatformLimit(raw: unknown): number | null {
  if (typeof raw !== "number" || !Number.isFinite(raw)) return null;
  const n = Math.round(raw);
  return Math.min(MAX_PLATFORM_LIMIT, Math.max(MIN_PLATFORM_LIMIT, n));
}

/**
 * 解析用户输入框的字符串（允许暂时为空，等 blur/Enter 校正）：
 * - 空/空白 → null（不立即变成 1，允许继续输入）；
 * - 非数字 → null（非法）；
 * - 数字 → 取整后夹紧 [1, 20]。
 */
export function parsePlatformLimitInput(raw: string): number | null {
  const s = raw.trim();
  if (s === "") return null;
  const n = Number(s);
  if (!Number.isFinite(n)) return null;
  return normalizePlatformLimit(n);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * 解析任意来源的 limits 数据（已 JSON.parse 的结果）：
 * - 非法整体 → 默认四平台 10；
 * - 逐字段：合法数字用该值，缺失/非法字段回退默认 10（单字段错误不丢其他字段）；
 * - 未知平台 key 被忽略；
 * - 返回新对象，绝不 mutate 输入。
 */
export function parsePlatformLimits(raw: unknown): PlatformLimitMap {
  const out: PlatformLimitMap = { ...DEFAULT_PLATFORM_LIMITS };
  if (!isPlainObject(raw)) return out;
  for (const platform of PLATFORM_ORDER) {
    const value = normalizePlatformLimit(raw[platform]);
    if (value !== null) out[platform] = value;
  }
  return out;
}

/** 从 storage 读取；损坏 JSON / 存储不可用 → 默认值（不崩溃）。 */
export function readPlatformLimits(storage: StorageLike): PlatformLimitMap {
  try {
    const raw = storage.getItem(PLATFORM_LIMITS_STORAGE_KEY);
    if (raw === null) return { ...DEFAULT_PLATFORM_LIMITS };
    return parsePlatformLimits(JSON.parse(raw));
  } catch {
    return { ...DEFAULT_PLATFORM_LIMITS };
  }
}

/** 写入 storage；失败返回 false（不阻止搜索）。 */
export function writePlatformLimits(storage: StorageLike, limits: PlatformLimitMap): boolean {
  try {
    storage.setItem(PLATFORM_LIMITS_STORAGE_KEY, JSON.stringify(limits));
    return true;
  } catch {
    return false;
  }
}

/** 更新单个平台（不可变）；非法值返回原对象（保持不变）。 */
export function updatePlatformLimit(
  limits: PlatformLimitMap,
  platform: PlatformSlug,
  raw: unknown
): PlatformLimitMap {
  const value = normalizePlatformLimit(raw);
  if (value === null) return limits;
  if (limits[platform] === value) return limits;
  return { ...limits, [platform]: value };
}

/** 恢复默认：四个平台全部 10（返回新对象）。 */
export function resetPlatformLimits(): PlatformLimitMap {
  return { ...DEFAULT_PLATFORM_LIMITS };
}

/** 只选择目标平台的数值（API 请求契约用；缺失目标回退默认 10）。 */
export function selectedPlatformLimits(
  limits: PlatformLimitMap,
  platforms: readonly PlatformSlug[]
): Partial<Record<PlatformSlug, number>> {
  const out: Partial<Record<PlatformSlug, number>> = {};
  for (const platform of platforms) {
    out[platform] = limits[platform] ?? DEFAULT_PLATFORM_LIMIT;
  }
  return out;
}
