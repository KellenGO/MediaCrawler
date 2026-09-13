import { useMemo, useState } from "react";
import { AlertTriangle, Bookmark, FolderHeart, Loader2, RefreshCw } from "lucide-react";
import { ResultTabs } from "@/components/search/ResultTabs";
import { BookmarkBackup } from "@/components/search/BookmarkBackup";
import { useBookmarks } from "@/hooks/useBookmarks";
import { useFavorites } from "@/hooks/useFavorites";
import type { PlatformSlug } from "@/types/search";
import { PLATFORM_COLORS, PLATFORM_LABELS, STATUS_LABELS } from "@/types/search";

const PLATFORMS: PlatformSlug[] = ["xhs", "douyin", "bilibili", "zhihu"];

function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : "收藏夹同步失败，请稍后重试。";
}

interface FavoritesPageProps {
  activeTab?: "local" | "remote";
  onTabChange?: (tab: "local" | "remote") => void;
  onNavigateAccounts: () => void;
}

export function FavoritesPage({ activeTab, onTabChange, onNavigateAccounts }: FavoritesPageProps) {
  const remote = useFavorites();
  const library = useBookmarks();
  const [localTab, setLocalTab] = useState<"local" | "remote">("local");
  const tab = activeTab ?? localTab;
  const setTab = (next: "local" | "remote") => {
    setLocalTab(next);
    onTabChange?.(next);
  };
  const [selected, setSelected] = useState<Set<PlatformSlug>>(() => new Set(PLATFORMS));
  const localResults = useMemo(() => library.items.map((item) => item.result), [library.items]);
  const data = remote.data;
  const fetchedAt = useMemo(() => Object.fromEntries(PLATFORMS.map((platform) => [platform, data?.completed_at ?? null])), [data]);

  const togglePlatform = (platform: PlatformSlug) => setSelected((before) => {
    const next = new Set(before);
    if (next.has(platform) && next.size > 1) next.delete(platform);
    else next.add(platform);
    return next;
  });

  return (
    <div className="preview-container favorites-page">
      <div className="collection-heading">
        <div className="page-heading">
          <div>
            <p className="eyebrow">YOUR COLLECTION</p>
            <h1>留住值得再看的内容</h1>
            <p className="description">{tab === "local" ? "给有用的内容一个位置，也记下自己的想法。" : "把不同平台的收藏放在一起，慢慢阅读。"}</p>
          </div>
          {tab === "local" && <details className="backup-details"><summary className="btn">备份管理</summary><BookmarkBackup library={library} /></details>}
        </div>

        <nav className="tabs collection-switch" aria-label="收藏类型">
          <button type="button" className={`tab ${tab === "local" ? "active" : ""}`} onClick={() => setTab("local")}>本地收藏 <span>{library.items.length}</span></button>
          <button type="button" className={`tab ${tab === "remote" ? "active" : ""}`} onClick={() => setTab("remote")}>跨平台收藏</button>
        </nav>

        {tab === "local" ? (
          <p className="collection-count">{library.items.length} 条已收藏 · 收藏和备注保存在当前浏览器</p>
        ) : (
          <>
            <div className="page-heading remote-heading">
              <div><h2>跨平台收藏</h2><p className="description">从已登录的平台读取收藏，可再保存到本地。</p></div>
              <button type="button" className="btn primary" disabled={remote.busy || !selected.size} onClick={() => void remote.sync([...selected])}>
                {remote.busy ? <Loader2 className="spinner" /> : <RefreshCw />}{remote.busy ? "正在同步" : data ? "重新同步" : "同步收藏"}
              </button>
            </div>
            <div className="scope collection-scope" aria-label="收藏同步平台">
              <span className="scope-label">同步范围</span>
              {PLATFORMS.map((platform) => <button key={platform} type="button" className="platform-choice" aria-pressed={selected.has(platform)} disabled={remote.busy} onClick={() => togglePlatform(platform)}>
                <i className="pd" style={{ backgroundColor: PLATFORM_COLORS[platform] }} />{PLATFORM_LABELS[platform]}<span className="check">{selected.has(platform) ? "✓" : ""}</span>
              </button>)}
            </div>
            <p className="collection-count">每个平台单次最多 20 条 · 同步只读取，不会修改平台收藏</p>
          </>
        )}
      </div>

      {library.error && <div className="status-line" role="alert"><AlertTriangle />{library.error}</div>}

      {tab === "local" ? (
        localResults.length ? <ResultTabs results={localResults} overall="completed" platforms={PLATFORMS} library={library} savedView jobId="bookmarks" /> : <div className="empty"><div className="empty-symbol"><Bookmark /></div><h2>收藏夹还空着</h2><p>遇到值得再读的内容，点一下结果右侧的收藏图标。</p></div>
      ) : remote.error ? (
        <div className="status-line" role="alert"><AlertTriangle />{errorMessage(remote.error)}<button type="button" className="text-link" onClick={onNavigateAccounts}>检查账号状态</button></div>
      ) : remote.busy && !data?.results.length ? (
        <div className="empty" role="status"><div className="empty-symbol"><Loader2 className="spinner" /></div><h2>正在整理你的收藏</h2><p>先获取列表，再补充内容信息。</p></div>
      ) : data ? (
        <>
          {Object.entries(data.platforms).some(([, info]) => info && !["succeeded", "empty", "running", "pending"].includes(info.status)) && <div className="status-line"><span className="status-message"><AlertTriangle />部分平台没有完成：{Object.entries(data.platforms).filter(([, info]) => info && !["succeeded", "empty", "running", "pending"].includes(info.status)).map(([platform, info]) => `${PLATFORM_LABELS[platform as PlatformSlug]} ${info?.error_summary || STATUS_LABELS[info!.status]}`).join("；")}</span><button type="button" className="text-link" onClick={onNavigateAccounts}>检查账号</button></div>}
          <ResultTabs results={data.results} overall={data.overall} jobId={data.job_id} platforms={Object.keys(data.platforms) as PlatformSlug[]} library={library} fetchedAt={fetchedAt} />
        </>
      ) : (
        <div className="empty"><div className="empty-symbol"><FolderHeart /></div><h2>把喜欢的内容，放到一起</h2><p>选择平台后点击同步，四处散落的收藏会汇到这里。</p><button type="button" className="btn" onClick={() => void remote.sync([...selected])}>同步收藏</button></div>
      )}
    </div>
  );
}
