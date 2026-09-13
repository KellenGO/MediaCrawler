import { useState, type ReactNode } from "react";
import { ArrowUpRight, ChevronDown } from "lucide-react";
import type { GroupedSource, UnifiedSearchResult } from "@/types/search";
import { PLATFORM_COLORS, PLATFORM_LABELS } from "@/types/search";
import { highlightSegments, orderedMetrics, safeContentUrl as safeUrl } from "@/lib/resultTools";

interface ResultCardProps {
  result: UnifiedSearchResult;
  index?: number;
  highlightQuery?: string;
  renderBookmark?: (result: UnifiedSearchResult) => ReactNode;
}

function Highlight({ text, query }: { text: string; query: string }) {
  return <>{highlightSegments(text, query).map((segment, index) => segment.matched
    ? <mark key={index} className="result-highlight">{segment.text}</mark>
    : segment.text)}</>;
}

function formatTime(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const minutes = Math.floor((Date.now() - date.getTime()) / 60000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return date.toLocaleDateString("zh-CN");
}

function formatCount(value: number): string {
  if (value >= 10000) return `${(value / 10000).toFixed(1)} 万`;
  return value.toLocaleString("zh-CN");
}

const CONTENT_TYPE_LABELS: Record<string, string> = {
  note: "图文笔记", video: "视频", short_video: "短视频", answer: "回答", article: "文章", post: "帖子",
};

function SourceLine({ source, query }: { source: GroupedSource; query: string }) {
  const url = safeUrl(source.url);
  const row = <div className="result-source-line"><i className="pd" style={{ backgroundColor: PLATFORM_COLORS[source.platform] }} /><span className="result-source-platform">{PLATFORM_LABELS[source.platform]}</span><span className="result-source-title"><Highlight text={source.title} query={query} /></span><span className="result-source-meta">{source.author}</span><ArrowUpRight className="result-source-arrow" /></div>;
  return url ? <a href={url} target="_blank" rel="noreferrer">{row}</a> : row;
}

export function ResultCard({ result, index = 0, highlightQuery = "", renderBookmark }: ResultCardProps) {
  const [groupExpanded, setGroupExpanded] = useState(false);
  const url = safeUrl(result.url);
  const groupedSources = result.grouped_sources && result.grouped_sources.length >= 2 ? result.grouped_sources : null;
  const title = <><Highlight text={result.title} query={highlightQuery} />{url && <ArrowUpRight />}</>;
  const metrics = orderedMetrics(result.metrics);
  const type = CONTENT_TYPE_LABELS[result.content_type] || result.content_type || "";

  return (
    <article className="result-row">
      <span className="result-number">{String(index + 1).padStart(2, "0")}</span>
      <div className="result-content">
        <h2>{url ? <a className="result-title" href={url} target="_blank" rel="noreferrer">{title}</a> : <span className="result-title">{title}</span>}</h2>
        {result.snippet && <p className="result-description"><Highlight text={result.snippet} query={highlightQuery} /></p>}
        <div className="result-meta">
          <span className="source"><i className="pd" style={{ backgroundColor: PLATFORM_COLORS[result.platform] }} />{groupedSources ? "跨平台聚合" : PLATFORM_LABELS[result.platform]}</span>
          {result.author && <span>{result.author}</span>}
          {result.published_at && <span>{formatTime(result.published_at)}</span>}
          {(type || metrics.length > 0) && <span className="meta-divider" />}
          {type && <span>{type}</span>}
          {metrics.map(({ key, label }) => <span key={key}>{label} {formatCount(result.metrics[key] || 0)}</span>)}
        </div>
        {groupedSources && <>
          <div className="result-group-summary"><span>{groupedSources.length} 个平台有同内容</span><button type="button" className="text-link" onClick={() => setGroupExpanded((value) => !value)}>{groupExpanded ? "收起平台版本" : "查看各平台版本"}<ChevronDown className={groupExpanded ? "rotate-180" : ""} /></button></div>
          {groupExpanded && <div className="result-sources">{groupedSources.map((source) => <SourceLine key={`${source.platform}-${source.content_id}`} source={source} query={highlightQuery} />)}</div>}
        </>}
      </div>
      {renderBookmark && <div className="row-actions">{renderBookmark(result)}</div>}
    </article>
  );
}
