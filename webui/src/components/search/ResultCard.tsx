import { useState, useMemo } from "react";
import { ExternalLink, ThumbsUp, MessageCircle, Heart, Eye, Coins, Tv } from "lucide-react";
import type { UnifiedSearchResult } from "@/types/search";
import { PLATFORM_LABELS, PLATFORM_ICONS, PLATFORM_COLORS } from "@/types/search";

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

function safeUrl(url: string): string | null {
  if (!url) return null;
  const u = url.trim();
  // Only allow http/https to known platform domains
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

export function ResultCard({ result }: ResultCardProps) {
  const [imgError, setImgError] = useState(false);
  const url = safeUrl(result.url);
  const platformColor = PLATFORM_COLORS[result.platform] || "#888";

  const metrics = useMemo(() => {
    const m = result.metrics || {};
    return [
      { key: "like_count", icon: Heart, label: "" },
      { key: "view_count", icon: Eye, label: "" },
      { key: "comment_count", icon: MessageCircle, label: "" },
      { key: "collect_count", icon: ThumbsUp, label: "" },
      { key: "coin_count", icon: Coins, label: "" },
      { key: "danmaku_count", icon: Tv, label: "" },
      { key: "share_count", icon: ExternalLink, label: "" },
    ]
      .filter(({ key }) => m[key] && m[key] > 0)
      .slice(0, 4);
  }, [result.metrics]);

  const inner = (
    <div className="flex gap-3 p-3 rounded-xl border border-cyber-border-subtle bg-cyber-bg-secondary hover:border-cyber-neon-cyan/50 hover:shadow-glow-cyan-sm transition-all cursor-pointer">
        <div className="flex-shrink-0 w-20 h-20 sm:w-24 sm:h-24 rounded-lg overflow-hidden bg-cyber-bg-tertiary border border-cyber-border-subtle">
          {!imgError && result.cover_url ? (
            <img src={result.cover_url} alt={result.title}
              referrerPolicy="no-referrer" loading="lazy"
              onError={() => setImgError(true)}
              className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-2xl"
              style={{ backgroundColor: platformColor + "20" }}>
              {PLATFORM_ICONS[result.platform] || "📄"}
            </div>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-start gap-2">
            <span className="flex-shrink-0 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold"
              style={{ backgroundColor: platformColor + "20", color: platformColor }}>
              {PLATFORM_LABELS[result.platform] || result.platform}
            </span>
            <h3 className="text-sm font-mono text-cyber-text-primary line-clamp-2 leading-snug group-hover:text-cyber-neon-cyan transition-colors">
              {result.title}
            </h3>
          </div>
          <div className="flex items-center gap-3 mt-1.5 text-xs text-cyber-text-muted font-mono">
            {result.author && <span>{result.author}</span>}
            {result.published_at && <span>{formatTime(result.published_at)}</span>}
          </div>
          {metrics.length > 0 && (
            <div className="flex items-center gap-3 mt-2">
              {metrics.map(({ key, icon: Icon }) => (
                <span key={key} className="flex items-center gap-1 text-xs text-cyber-text-muted font-mono">
                  <Icon className="w-3 h-3" /><span>{formatCount(result.metrics[key] || 0)}</span>
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex-shrink-0 flex items-center">
          <ExternalLink className="w-4 h-4 text-cyber-text-muted opacity-0 group-hover:opacity-100 transition-opacity" />
        </div>
      </div>
  );

  if (url) {
    return (
      <a href={url} target="_blank" rel="noopener noreferrer" className="block group">
        {inner}
      </a>
    );
  }
  return <div className="block group">{inner}</div>;
}
