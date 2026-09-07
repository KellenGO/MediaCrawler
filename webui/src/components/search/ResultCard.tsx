import { useState, useMemo, type ReactNode } from "react";
import { ArrowUpRight, ChevronDown, Heart, Eye, MessageCircle, ThumbsUp, Coins, Tv, Share2 } from "lucide-react";
import type { UnifiedSearchResult } from "@/types/search";
import { PLATFORM_LABELS, PLATFORM_COLORS } from "@/types/search";
import { highlightSegments, safeContentUrl as safeUrl } from "@/lib/resultTools";

interface ResultCardProps {
  result: UnifiedSearchResult;
  highlightQuery?: string;
  renderBookmark?: (result: UnifiedSearchResult) => ReactNode;
}

function Highlight({ text, query }: { text: string; query: string }) {
  return <>{highlightSegments(text, query).map((segment, index) => segment.matched
    ? <mark key={index} className="rounded-sm bg-amber-100 text-amber-950">{segment.text}</mark>
    : segment.text)}</>;
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

function metricSummary(metrics: Record<string, number>): string {
  const labels: Array<[string, string]> = [
    ["comment_count", "评论"],
    ["collect_count", "收藏"],
    ["coin_count", "投币"],
    ["share_count", "分享"],
    ["like_count", "点赞"],
    ["danmaku_count", "弹幕"],
    ["view_count", "播放"],
  ];
  return labels
    .filter(([key]) => (metrics[key] || 0) > 0)
    .slice(0, 2)
    .map(([key, label]) => `${label} ${formatCount(metrics[key] || 0)}`)
    .join(" · ");
}

export function ResultCard({ result, highlightQuery = "", renderBookmark }: ResultCardProps) {
  const [imgError, setImgError] = useState(false);
  const [groupExpanded, setGroupExpanded] = useState(false);
  const url = safeUrl(result.url);
  const platformColor = PLATFORM_COLORS[result.platform] || "#4ca4dc";
  const contentType = CONTENT_TYPE_LABELS[result.content_type] || result.content_type || "";
  const groupedSources = result.grouped_sources && result.grouped_sources.length >= 2
    ? result.grouped_sources
    : null;
  const groupedContentTypes = groupedSources
    ? [...new Set(groupedSources.map((source) => CONTENT_TYPE_LABELS[source.content_type] || source.content_type).filter(Boolean))].join(" / ")
    : "";

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

  if (groupedSources) {
    return (
      <div className="relative overflow-hidden rounded-[18px] border border-brand/35 border-l-[3px] bg-[linear-gradient(180deg,rgba(228,243,252,0.58)_0%,rgba(255,255,255,0.9)_48%,rgba(255,255,255,0.96)_100%)] shadow-[0_8px_26px_rgba(50,105,145,0.08)] hover:border-brand/55 hover:shadow-[0_12px_34px_rgba(50,105,145,0.13)] transition-all">
        <div className="flex items-center justify-between gap-3 px-3 sm:px-3.5 pt-3">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-brand/20 bg-brand-soft px-2.5 py-1 text-[10.5px] font-extrabold tracking-[0.01em] text-brand-strong">
            <span className="h-1.5 w-1.5 rounded-full bg-brand shadow-[0_0_0_3px_rgba(76,164,220,0.14)]" />
            跨平台聚合
          </span>
          <div className="flex items-center gap-2"><span className="text-[11px] font-medium text-cyber-text-muted">
            {groupedSources.length} 个平台同内容
          </span>{renderBookmark?.(result)}</div>
        </div>

        <div className="grid grid-cols-[104px_minmax(0,1fr)] sm:grid-cols-[144px_minmax(0,1fr)_auto] gap-3 sm:gap-[18px] p-3 sm:p-3.5 pt-2.5">
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

          <div className="min-w-0 py-1">
            <div className="flex items-center gap-2.5 mb-1.5">
              <span className="text-[11.5px] font-bold text-brand-strong">多平台</span>
              {groupedContentTypes && <span className="text-[11px] text-cyber-text-muted">{groupedContentTypes}</span>}
            </div>
            <h3 className="text-[15px] sm:text-[16.5px] font-semibold leading-[1.55] tracking-[-0.01em] text-cyber-text-primary line-clamp-2">
              <Highlight text={result.title} query={highlightQuery} />
            </h3>
            <div className="flex items-center gap-2.5 mt-2 text-[12px] text-cyber-text-secondary">
              {result.author && (
                <span className="flex items-center gap-1.5 min-w-0">
                  <span className="w-[18px] h-[18px] rounded-full grid place-items-center text-[9.5px] font-bold text-white flex-shrink-0 bg-brand">
                    {result.author.trim().charAt(0)}
                  </span>
                  <span className="truncate">{result.author}</span>
                </span>
              )}
              {result.published_at && <span className="flex-shrink-0">{formatTime(result.published_at)}</span>}
            </div>
            {result.snippet && (
              <p className="mt-1 text-[12.5px] leading-[1.55] text-cyber-text-secondary line-clamp-3">
                <Highlight text={result.snippet} query={highlightQuery} />
              </p>
            )}
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
            <div className="mt-3 flex flex-wrap items-center gap-1.5 rounded-[12px] border border-brand/15 bg-white/60 p-2">
              <span className="mr-1 text-[10.5px] font-semibold text-cyber-text-muted">来源</span>
              {groupedSources.map((source) => (
                <span
                  key={`${source.platform}-${source.content_id}`}
                  className="px-2 py-0.5 rounded-full text-[10.5px] font-semibold border"
                  style={{
                    color: PLATFORM_COLORS[source.platform] || "#4ca4dc",
                    borderColor: `${PLATFORM_COLORS[source.platform] || "#4ca4dc"}55`,
                    backgroundColor: `${PLATFORM_COLORS[source.platform] || "#4ca4dc"}0d`,
                  }}
                >
                  {PLATFORM_LABELS[source.platform] || source.platform}
                </span>
              ))}
            </div>
            <div className="flex items-center justify-between gap-3 mt-2">
              <span className="text-[10.5px] text-cyber-text-muted">同一内容的不同平台版本</span>
              <button
                type="button"
                aria-expanded={groupExpanded}
                onClick={() => setGroupExpanded((expanded) => !expanded)}
                className="inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11.5px] font-semibold text-brand-strong hover:bg-brand-soft"
              >
                {groupExpanded ? "收起平台版本" : "查看各平台版本"}
                <ChevronDown className={`w-3.5 h-3.5 transition-transform ${groupExpanded ? "rotate-180" : ""}`} />
              </button>
            </div>
          </div>
        </div>

        {groupExpanded && (
          <div className="border-t border-brand/15 bg-white/55 px-3 sm:px-3.5 py-2">
            {groupedSources.map((source) => {
              const sourceUrl = safeUrl(source.url);
              const sourceColor = PLATFORM_COLORS[source.platform] || "#4ca4dc";
              const sourceType = CONTENT_TYPE_LABELS[source.content_type] || source.content_type || "";
              const sourceRow = (
                <div className="flex items-start gap-2.5 min-w-0 py-2.5">
                  <span className="w-1.5 h-1.5 mt-2 rounded-full flex-shrink-0" style={{ backgroundColor: sourceColor }} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-[11.5px] font-bold flex-shrink-0" style={{ color: sourceColor }}>
                        {PLATFORM_LABELS[source.platform] || source.platform}
                      </span>
                      {sourceType && <span className="text-[10.5px] text-cyber-text-muted flex-shrink-0">{sourceType}</span>}
                      <span className="text-[12px] text-cyber-text-primary truncate"><Highlight text={source.title} query={highlightQuery} /></span>
                    </div>
                    <div className="flex items-center gap-2 mt-1 text-[11px] text-cyber-text-muted truncate">
                      {source.author && <span className="truncate">{source.author}</span>}
                      {source.published_at && <span className="flex-shrink-0">{formatTime(source.published_at)}</span>}
                    </div>
                    {source.snippet && (
                      <p className="mt-1 text-[11.5px] leading-[1.5] text-cyber-text-secondary line-clamp-2"><Highlight text={source.snippet} query={highlightQuery} /></p>
                    )}
                    {metricSummary(source.metrics) && (
                      <p className="mt-1 text-[10.5px] text-cyber-text-muted truncate">{metricSummary(source.metrics)}</p>
                    )}
                  </div>
                  <ArrowUpRight className="w-3.5 h-3.5 mt-1 flex-shrink-0 text-cyber-text-muted" />
                </div>
              );
              return <div key={`${source.platform}-${source.content_id}`} className="flex items-center gap-2 border-b last:border-b-0 border-cyber-border-subtle">
                {sourceUrl ? <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="block min-w-0 flex-1 hover:bg-cyber-bg-tertiary/60">{sourceRow}</a>
                  : <div className="min-w-0 flex-1">{sourceRow}</div>}
                {renderBookmark?.({ ...source, grouped_sources: null })}
              </div>;
            })}
          </div>
        )}
      </div>
    );
  }

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
        <div className="flex items-center gap-2.5 mb-1.5 pr-8">
          <span className="text-[11.5px] font-bold" style={{ color: platformColor }}>
            {PLATFORM_LABELS[result.platform] || result.platform}
          </span>
          {contentType && <span className="text-[11px] text-cyber-text-muted">{contentType}</span>}
        </div>
        <h3 className="text-[15px] sm:text-[16.5px] font-semibold leading-[1.55] tracking-[-0.01em] text-cyber-text-primary line-clamp-2">
          <Highlight text={result.title} query={highlightQuery} />
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
        {result.snippet && (
          <p className="mt-1 text-[12.5px] leading-[1.55] text-cyber-text-secondary line-clamp-3">
            <Highlight text={result.snippet} query={highlightQuery} />
          </p>
        )}
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

  return <div className="relative">
    {url ? <a href={url} target="_blank" rel="noopener noreferrer" className="block">{inner}</a> : inner}
    {renderBookmark && <div className="absolute right-3 top-3">{renderBookmark(result)}</div>}
  </div>;
}
