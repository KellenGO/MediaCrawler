/**
 * 按平台独立搜索数量 hook（Round 15）。
 *
 * 以 localStorage 为唯一持久化来源：修改后立即更新状态并写回 storage
 * （设置页与搜索页条件挂载，各自读取最新 storage，无需跨页同步协议）。
 */

import { useCallback, useEffect, useState } from "react";
import {
  readPlatformLimits,
  resetPlatformLimits,
  updatePlatformLimit,
  writePlatformLimits,
  type PlatformLimitMap,
} from "@/lib/platformLimits";
import type { PlatformSlug } from "@/types/search";

export interface UsePlatformLimitsResult {
  limits: PlatformLimitMap;
  /** 更新单个平台数量（非法值忽略；立即写回 localStorage）。 */
  setLimit: (platform: PlatformSlug, raw: unknown) => void;
  /** 恢复四个平台为默认 10（不自动发起搜索）。 */
  resetAll: () => void;
}

export function usePlatformLimits(): UsePlatformLimitsResult {
  const [limits, setLimits] = useState<PlatformLimitMap>(() =>
    readPlatformLimits(localStorage)
  );

  // 修改后立即持久化（失败静默，不阻止搜索）。
  useEffect(() => {
    writePlatformLimits(localStorage, limits);
  }, [limits]);

  const setLimit = useCallback((platform: PlatformSlug, raw: unknown) => {
    setLimits((prev) => updatePlatformLimit(prev, platform, raw));
  }, []);

  const resetAll = useCallback(() => {
    setLimits(resetPlatformLimits());
  }, []);

  return { limits, setLimit, resetAll };
}
