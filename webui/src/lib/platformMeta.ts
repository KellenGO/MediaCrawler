import type { PlatformSlug } from "../types/search";

/**
 * 支持平台的**唯一来源**。
 *
 * 数组顺序就是 UI 展示顺序，改这里等于同时改搜索页、收藏页、账号页、
 * 统计条与批量同步的顺序 —— 这是刻意的（历史上这四个字面量在 8 个文件里
 * 各写了一遍，加一个平台要改 8 处，且很容易只改一半）。
 *
 * 类型故意用可变的 `PlatformSlug[]`：各调用点有的声明成 `readonly`
 * 有的声明成可变数组，用可变类型才能同时满足两边。
 */
export const PLATFORM_SLUGS: PlatformSlug[] = ["xhs", "douyin", "bilibili", "zhihu"];

/** 判断一个字符串是否是受支持的平台。 */
export function isPlatformSlug(value: unknown): value is PlatformSlug {
  return typeof value === "string" && (PLATFORM_SLUGS as string[]).includes(value);
}
