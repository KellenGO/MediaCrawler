/**
 * Round 15 按平台独立搜索数量测试 —— 直接 import 编译后的生产模块
 * （webui/src/lib/platformLimits.ts），不复制任何生产逻辑。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import {
  DEFAULT_PLATFORM_LIMITS,
  MAX_PLATFORM_LIMIT,
  MIN_PLATFORM_LIMIT,
  PLATFORM_LIMITS_STORAGE_KEY,
  normalizePlatformLimit,
  parsePlatformLimitInput,
  parsePlatformLimits,
  readPlatformLimits,
  resetPlatformLimits,
  selectedPlatformLimits,
  updatePlatformLimit,
  writePlatformLimits,
  type PlatformLimitMap,
  type StorageLike,
} from "../src/lib/platformLimits.js";

class MemoryStorage implements StorageLike {
  private map = new Map<string, string>();
  getItem(key: string): string | null {
    return this.map.has(key) ? this.map.get(key)! : null;
  }
  setItem(key: string, value: string): void {
    this.map.set(key, value);
  }
  removeItem(key: string): void {
    this.map.delete(key);
  }
}

// ── 默认值与边界 ───────────────────────────────────────────────────────

test("默认四个平台都是 10", () => {
  assert.deepEqual(DEFAULT_PLATFORM_LIMITS, {
    xhs: 10, douyin: 10, bilibili: 10, zhihu: 10,
  });
});

test("合法的 1 和 20 被接受", () => {
  assert.equal(normalizePlatformLimit(1), 1);
  assert.equal(normalizePlatformLimit(20), 20);
  assert.equal(parsePlatformLimitInput("1"), 1);
  assert.equal(parsePlatformLimitInput("20"), 20);
});

test("0、21、负数按前端规则校正（夹紧）", () => {
  assert.equal(normalizePlatformLimit(0), 1);
  assert.equal(normalizePlatformLimit(21), 20);
  assert.equal(normalizePlatformLimit(-5), 1);
  assert.equal(parsePlatformLimitInput("0"), 1);
  assert.equal(parsePlatformLimitInput("21"), 20);
  assert.equal(parsePlatformLimitInput("-3"), 1);
});

test("小数转为整数（四舍五入）", () => {
  assert.equal(normalizePlatformLimit(5.4), 5);
  assert.equal(normalizePlatformLimit(5.5), 6);
  assert.equal(parsePlatformLimitInput("7.6"), 8);
  assert.equal(parsePlatformLimitInput("7.2"), 7);
});

// ── 非法值判定 ─────────────────────────────────────────────────────────

test("NaN、Infinity、boolean、空字符串、null、对象、数组非法", () => {
  for (const bad of [NaN, Infinity, -Infinity, true, false, null, undefined,
    "", "abc", {}, [], { x: 1 }, [5]]) {
    assert.equal(normalizePlatformLimit(bad), null, `normalize(${String(bad)}) 必须为 null`);
  }
  assert.equal(parsePlatformLimitInput(""), null);
  assert.equal(parsePlatformLimitInput("  "), null);
  assert.equal(parsePlatformLimitInput("abc"), null);
});

// ── 读取与恢复 ─────────────────────────────────────────────────────────

test("损坏 JSON 回退默认", () => {
  const storage = new MemoryStorage();
  storage.setItem(PLATFORM_LIMITS_STORAGE_KEY, "{broken json!!");
  assert.deepEqual(readPlatformLimits(storage), DEFAULT_PLATFORM_LIMITS);
  storage.setItem(PLATFORM_LIMITS_STORAGE_KEY, JSON.stringify("not-an-object"));
  assert.deepEqual(readPlatformLimits(storage), DEFAULT_PLATFORM_LIMITS);
});

test("一个字段非法时，其他合法字段保留", () => {
  const parsed = parsePlatformLimits({
    xhs: 5, douyin: "bad", bilibili: 8, zhihu: true,
  });
  assert.equal(parsed.xhs, 5);
  assert.equal(parsed.bilibili, 8);
  assert.equal(parsed.douyin, 10); // 非法字段回退默认
  assert.equal(parsed.zhihu, 10);
});

test("缺失字段回退 10；未知平台被过滤", () => {
  const parsed = parsePlatformLimits({ xhs: 3, myspace: 7, bogus: 9 });
  assert.equal(parsed.xhs, 3);
  assert.equal(parsed.douyin, 10);
  assert.equal(parsed.bilibili, 10);
  assert.equal(parsed.zhihu, 10);
  assert.equal("myspace" in parsed, false);
});

test("readPlatformLimits 按字段恢复：部分平台有效时其余用默认", () => {
  const storage = new MemoryStorage();
  storage.setItem(PLATFORM_LIMITS_STORAGE_KEY, JSON.stringify({ xhs: 3, douyin: 12 }));
  const limits = readPlatformLimits(storage);
  assert.equal(limits.xhs, 3);
  assert.equal(limits.douyin, 12);
  assert.equal(limits.bilibili, 10);
  assert.equal(limits.zhihu, 10);
});

// ── 修改 / 恢复默认 / 持久化 ───────────────────────────────────────────

test("修改一个平台不改变其他平台", () => {
  const base: PlatformLimitMap = { ...DEFAULT_PLATFORM_LIMITS };
  const next = updatePlatformLimit(base, "xhs", 5);
  assert.equal(next.xhs, 5);
  assert.equal(next.douyin, 10);
  assert.equal(next.bilibili, 10);
  assert.equal(next.zhihu, 10);
  assert.equal(base.xhs, 10, "输入对象不被 mutate");
});

test("updatePlatformLimit 非法值返回原对象（不改变）", () => {
  const base: PlatformLimitMap = { ...DEFAULT_PLATFORM_LIMITS };
  assert.equal(updatePlatformLimit(base, "xhs", "bad"), base);
  assert.equal(updatePlatformLimit(base, "xhs", null), base);
  assert.equal(updatePlatformLimit(base, "xhs", NaN), base);
  // 越界值按前端规则夹紧后生效（0→1、21→20）
  const clampedLow = updatePlatformLimit(base, "xhs", 0);
  assert.equal(clampedLow.xhs, 1);
  const clampedHigh = updatePlatformLimit(base, "xhs", 21);
  assert.equal(clampedHigh.xhs, 20);
});

test("恢复默认得到四个 10", () => {
  const next = resetPlatformLimits();
  assert.deepEqual(next, { xhs: 10, douyin: 10, bilibili: 10, zhihu: 10 });
});

test("localStorage setItem 抛错不崩溃（返回 false）", () => {
  const storage: StorageLike = {
    getItem: () => null,
    setItem: () => { throw new Error("QuotaExceededError"); },
    removeItem: () => {},
  };
  assert.equal(writePlatformLimits(storage, { ...DEFAULT_PLATFORM_LIMITS }), false);
  // 读不受写失败影响
  assert.deepEqual(readPlatformLimits(storage), DEFAULT_PLATFORM_LIMITS);
});

// ── selectedPlatformLimits ─────────────────────────────────────────────

test("selectedPlatformLimits 只选择目标平台且数值正确", () => {
  const limits: PlatformLimitMap = { xhs: 5, douyin: 20, bilibili: 8, zhihu: 12 };
  assert.deepEqual(selectedPlatformLimits(limits, ["xhs", "zhihu"]), { xhs: 5, zhihu: 12 });
  assert.deepEqual(selectedPlatformLimits(limits, ["douyin"]), { douyin: 20 });
  assert.deepEqual(selectedPlatformLimits(limits, []), {});
});

test("selectedPlatformLimits 不 mutate 输入对象", () => {
  const limits: PlatformLimitMap = { xhs: 5, douyin: 10, bilibili: 10, zhihu: 10 };
  const snapshot = JSON.stringify(limits);
  selectedPlatformLimits(limits, ["xhs"]);
  assert.equal(JSON.stringify(limits), snapshot);
});

// ── parsePlatformLimits 不 mutate 输入 ─────────────────────────────────

test("parsePlatformLimits 输入对象不被 mutate", () => {
  const raw = { xhs: 5, douyin: "bad", bilibili: 8 };
  const snapshot = JSON.stringify(raw);
  parsePlatformLimits(raw);
  assert.equal(JSON.stringify(raw), snapshot);
});

// ── 常量边界 ───────────────────────────────────────────────────────────

test("MIN/MAX 常量为 1 和 20", () => {
  assert.equal(MIN_PLATFORM_LIMIT, 1);
  assert.equal(MAX_PLATFORM_LIMIT, 20);
});

test("完整写入后读取保持一致", () => {
  const storage = new MemoryStorage();
  const limits: PlatformLimitMap = { xhs: 3, douyin: 6, bilibili: 9, zhihu: 12 };
  assert.equal(writePlatformLimits(storage, limits), true);
  assert.deepEqual(readPlatformLimits(storage), limits);
  // 未知平台写入被读取端过滤
  storage.setItem(PLATFORM_LIMITS_STORAGE_KEY, JSON.stringify({ xhs: 4, evil: 99 }));
  assert.deepEqual(readPlatformLimits(storage), { xhs: 4, douyin: 10, bilibili: 10, zhihu: 10 });
});
