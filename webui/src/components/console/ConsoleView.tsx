/**
 * 爬虫控制台视图（Phase 5.2）：CrawlerConfigPanel + MainContent 打包为一个
 * lazy view，App.tsx 用 React.lazy 按需加载 —— 首页（搜索页）不加载该 chunk。
 */

import { CrawlerConfigPanel } from "@/components/config/CrawlerConfigPanel";
import { MainContent } from "@/components/layout/MainContent";

export default function ConsoleView() {
  return (
    <div className="flex flex-col gap-3 pt-4">
      {/* Config Panel - Primary Action Area (Always Expanded) */}
      <CrawlerConfigPanel />

      {/* Console - Collapsible Terminal（终端保持深色等宽） */}
      <div className="h-[calc(100dvh-230px)] min-h-[380px] overflow-hidden rounded-[16px] border border-cyber-border-subtle bg-[#0d1117]">
        <MainContent />
      </div>
    </div>
  );
}
