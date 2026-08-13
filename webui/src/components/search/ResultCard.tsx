import { useState, useMemo } from "react";
import { ArrowUpRight, Heart, Eye, MessageCircle, ThumbsUp, Coins, Tv, Share2 } from "lucide-react";
import type { UnifiedSearchResult } from "@/types/search";
import { PLATFORM_LABELS, PLATFORM_COLORS } from "@/types/search";

interface ResultCardProps {
  result: UnifiedSearchResult;
}

function formatTime(iso: string | null): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    const minutes = Math.floor(diff / 60000);
    if (minutes < 1) return "刚刚";
    if (minutes < 60) return `${minutes}分钟前`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}小时前`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}天前`;
    return d.toLocaleDateString("zh-CN");
  } catch {
    return "";
  }
}

function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + "万";
  if (n >= 1000) return (n / 1000).toFixed(1) + "k";
  return String(n);
}

/** 安全 URL 校验（Round 12 逻辑原样保留）：仅允许 http/https 且域名在平台白名单内。 */
function safeUrl(url: string): string | null {
  if (!url) return null;
  const u = url.trim();
  const ALLOWED_DOMAINS = [
    "xiaohongshu.com", "xhslink.com", "rednote.com",
    "douyin.com", "bilibili.com", "zhihu.com", "zhuanlan.zhihu.com",
  ];
  if (u.startsWith("http://") || u.startsWith("https://")) {
    try {
      const host = new URL(u).hostname;
      if (ALLOWED_DOMAINS.some(d => host === d || host.endsWith("." + d))) {
        return u;
      }
    } catch {
      return null;
    }
  }
  return null;
}

/** 内容类型展示文案（原始 slug → 中文；其余原样）。 */
const CONTENT_TYPE_LABELS: Record<string, string> = {
  note: "图文笔记",
  video: "视频",
  short_video: "短视频",
  answer: "回答",
  article: "文章",
  post: "帖子",
};

/** 封面占位图（效果稿：平台色克制渐变 + 圆形装饰）。 */
function CoverPlaceholder({ platform }: { platform: string }) {
  const color = PLATFORM_COLORS[platform as keyof typeof PLATFORM_COLORS] || "#4ca4dc";
  return (
    <div
      className="absolute inset-0 overflow-hidden"
      style={{ background: `linear-gradient(135deg, ${color}e6, ${color}59)` }}
    >
      <span
        className="absolute rounded-full bg-white/30"
        style={{ width: 84, height: 84, right: -15, top: -18 }}
      />
      <span
        className="absolute rounded-full bg-white/25"
        style={{ width: 48, height: 48, left: 20, bottom: -15 }}
      />
    </div>
  );
}

export function ResultCard({ result }: ResultCardProps) {
  const [imgError, setImgError] = useState(false);
  const url = safeUrl(result.url);
  const platformColor = PLATFORM_COLORS[result.platform] || "#4ca4dc";
  const contentType = CONTENT_TYPE_LABELS[result.content_type] || result.content_type || "";

  const metrics = useMemo(() => {
    const m = result.metrics || {};
    return [
      { key: "like_count", icon: Heart, label: "" },
      { key: "view_count", icon: Eye, label: "" },
      { key: "comment_count", icon: MessageCircle, label: "" },
      { key: "collect_count", icon: ThumbsUp, label: "" },
      { key: "coin_count", icon: Coins, label: "" },
      { key: "danmaku_count", icon: Tv, label: "" },
      { key: "share_count", icon: Share2, label: "" },
    ]
      .filter(({ key }) => m[key] && m[key] > 0)
      .slice(0, 4);
  }, [result.metrics]);

  const inner = (
    <div className="group grid grid-cols-[104px_minmax(0,1fr)] sm:grid-cols-[144px_minmax(0,1fr)_auto] gap-3 sm:gap-[18px] p-3 sm:p-3.5 rounded-[18px] border border-cyber-border-subtle bg-cyber-bg-secondary hover:border-cyber-border-default hover:shadow-[0_10px_30px_rgba(50,105,145,0.09)] hover:-translate-y-0.5 transition-all cursor-pointer">
      {/* 封面：尺寸统一 */}
      <div className="relative w-[104px] h-[96px] sm:w-[144px] sm:h-[104px] rounded-[12px] overflow-hidden bg-cyber-bg-tertiary flex-shrink-0">
        {!imgError && result.cover_url ? (
          <img
            src={result.cover_url}
            alt={result.title}
            referrerPolicy="no-referrer"
            loading="lazy"
            onError={() => setImgError(true)}
            className="w-full h-full object-cover"
          />
        ) : (
          <CoverPlaceholder platform={result.platform} />
        )}
      </div>

      {/* 中间信息 */}
      <div className="min-w-0 py-1">
        <div className="flex items-center gap-2.5 mb-1.5">
          <span className="text-[11.5px] font-bold" style={{ color: platformColor }}>
            {PLATFORM_LABELS[result.platform] || result.platform}
          </span>
          {contentType && <span className="text-[11px] text-cyber-text-muted">{contentType}</span>}
        </div>
        <h3 className="text-[15px] sm:text-[16.5px] font-semibold leading-[1.55] tracking-[-0.01em] text-cyber-text-primary line-clamp-2">
          {result.title}
        </h3>
        <div className="flex items-center gap-2.5 mt-2 text-[12px] text-cyber-text-secondary">
          {result.author && (
            <span className="flex items-center gap-1.5 min-w-0">
              <span
                className="w-[18px] h-[18px] rounded-full grid place-items-center text-[9.5px] font-bold text-white flex-shrink-0"
                style={{ backgroundColor: platformColor }}
              >
                {result.author.trim().charAt(0)}
              </span>
              <span className="truncate">{result.author}</span>
            </span>
          )}
          {result.published_at && <span className="flex-shrink-0">{formatTime(result.published_at)}</span>}
        </div>
        {metrics.length > 0 && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-2.5 text-[11.5px] text-cyber-text-muted">
            {metrics.map(({ key, icon: Icon }) => (
              <span key={key} className="flex items-center gap-1">
                <Icon className="w-3 h-3" />
                <span>{formatCount(result.metrics[key] || 0)}</span>
              </span>
            ))}
          </div>
        )}
      </div>

      {/* 右侧跳转图标 */}
      <span className="hidden sm:grid place-items-center self-center w-[32px] h-[32px] rounded-full border border-cyber-border-subtle text-cyber-text-secondary group-hover:text-brand-strong group-hover:border-brand group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-all">
        <ArrowUpRight className="w-4 h-4" />
      </span>
    </div>
  );

  if (url) {
    return (
      <a href={url} target="_blank" rel="noopener noreferrer" className="block">
        {inner}
      </a>
    );
  }
  return <div>{inner}</div>;
}
