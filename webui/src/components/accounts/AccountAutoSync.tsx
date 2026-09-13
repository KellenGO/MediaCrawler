/**
 * 打开程序时自动检测并同步登录状态（无 UI 交互，只在应用根部挂载一次）。
 *
 * 结果通过 toast 汇报；同步进行中在页面顶部显示一条细提示，让"刚打开程序
 * 有几秒钟在忙"这件事是可见的。
 */

import { Loader2 } from "lucide-react";

import { useAutoAccountSync } from "@/hooks/useAutoAccountSync";

export function AccountAutoSync() {
  const { running, note } = useAutoAccountSync();
  if (!running && !note) return null;
  return (
    <div className="auto-sync-notice" role="status" aria-live="polite">
      {running && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
      {running ? (note || "正在自动同步登录状态…") : note}
    </div>
  );
}
