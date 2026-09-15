import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Bookmark, Check, FolderHeart, FolderPlus, Loader2, Pencil, RefreshCw, Trash2, X,
} from "lucide-react";
import { ResultTabs } from "@/components/search/ResultTabs";
import { BookmarkBackup } from "@/components/search/BookmarkBackup";
import { useBookmarks } from "@/hooks/useBookmarks";
import { useFavorites } from "@/hooks/useFavorites";
import { parseGroupKey } from "@/lib/resultTools";
import type { PlatformSlug } from "@/types/search";
import { PLATFORM_COLORS, PLATFORM_LABELS, STATUS_LABELS } from "@/types/search";
import { PLATFORM_SLUGS } from "@/lib/platformMeta";

const PLATFORMS = PLATFORM_SLUGS;


function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : "收藏夹同步失败，请稍后重试。";
}

/** 本地收藏左侧选择：全部 / 未分类 / 某个收藏夹。 */
type LibrarySelection = { kind: "all" } | { kind: "unclassified" } | { kind: "collection"; id: number };

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

  const [selection, setSelection] = useState<LibrarySelection>({ kind: "all" });
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [selectionResetKey, setSelectionResetKey] = useState(0);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [renaming, setRenaming] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [moving, setMoving] = useState(false);

  const unclassifiedCount = useMemo(
    () => library.items.filter((item) => item.collections.length === 0).length,
    [library.items],
  );
  const visibleItems = useMemo(() => {
    if (selection.kind === "all") return library.items;
    if (selection.kind === "unclassified") return library.items.filter((item) => item.collections.length === 0);
    return library.items.filter((item) => item.collections.some((tag) => tag.id === selection.id));
  }, [library.items, selection]);
  const localResults = useMemo(() => visibleItems.map((item) => item.result), [visibleItems]);
  const activeCollection = selection.kind === "collection"
    ? library.collections.find((item) => item.id === selection.id) ?? null
    : null;

  // 收藏夹被删除后回到「全部收藏」
  useEffect(() => {
    if (selection.kind === "collection" && !library.collections.some((item) => item.id === selection.id)) {
      setSelection({ kind: "all" });
    }
  }, [library.collections, selection]);

  // 切换选择时清空勾选
  useEffect(() => {
    setSelectedKeys([]);
  }, [selection]);

  const data = remote.data;
  const fetchedAt = useMemo(
    () => Object.fromEntries(PLATFORMS.map((platform) => [platform, data?.platforms[platform]?.synced_at ?? null])),
    [data],
  );

  const togglePlatform = (platform: PlatformSlug) => setSelected((before) => {
    const next = new Set(before);
    if (next.has(platform) && next.size > 1) next.delete(platform);
    else next.add(platform);
    return next;
  });

  const submitNewCollection = async () => {
    const name = newName.trim();
    if (!name) return;
    setMoving(true);
    const ok = await library.createCollection(name);
    setMoving(false);
    if (ok) {
      setNewName("");
      setCreating(false);
    }
  };

  const submitRename = async (id: number) => {
    const name = renameValue.trim();
    if (!name) return;
    setMoving(true);
    const ok = await library.renameCollection(id, name);
    setMoving(false);
    if (ok) {
      setRenaming(null);
      setRenameValue("");
    }
  };

  /**
   * 结果列表按「分组」勾选（groupKey 是 JSON 数组串），而收藏库接口只认单条
   * `platform|content_id`，所以批量操作前统一转换并去重。
   */
  const selectedItemKeys = useMemo(
    () => [...new Set(selectedKeys.flatMap(parseGroupKey))],
    [selectedKeys],
  );

  const batchAdd = async (collectionId: number) => {
    if (!selectedItemKeys.length) return;
    setMoving(true);
    const ok = await library.addToCollection(selectedItemKeys, collectionId);
    setMoving(false);
    if (ok) {
      setSelectedKeys([]);
      setSelectionResetKey((value) => value + 1);
    }
  };

  const batchRemove = async (collectionId: number) => {
    if (!selectedItemKeys.length) return;
    setMoving(true);
    const ok = await library.removeFromCollection(selectedItemKeys, collectionId);
    setMoving(false);
    if (ok) {
      setSelectedKeys([]);
      setSelectionResetKey((value) => value + 1);
    }
  };

  const localHeading = activeCollection
    ? `「${activeCollection.name}」共 ${activeCollection.item_count} 条 · 收藏与备注保存在本机`
    : selection.kind === "unclassified"
      ? `${visibleItems.length} 条未分类 · 可以把它们整理进收藏夹`
      : `${library.items.length} 条已收藏 · 收藏与备注保存在本机数据库`;

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
          <p className="collection-count">{localHeading}</p>
        ) : (
          <>
            <div className="page-heading remote-heading">
              <div><h2>跨平台收藏</h2><p className="description">从已登录的平台读取收藏，可再保存到本地。</p></div>
              <button type="button" className="btn primary" disabled={remote.cancelling || (!remote.canCancel && (remote.busy || !selected.size))} onClick={() => remote.canCancel ? void remote.cancel() : void remote.sync([...selected])}>
                {remote.busy || remote.cancelling ? <Loader2 className="spinner" aria-hidden="true" /> : <RefreshCw />}
                {remote.cancelling ? "正在取消" : remote.canCancel ? "正在同步 · 取消" : remote.busy ? "正在启动同步" : data ? "重新同步" : "同步收藏"}
              </button>
            </div>
            <div className="scope collection-scope" aria-label="收藏同步平台">
              <span className="scope-label">同步范围</span>
              {PLATFORMS.map((platform) => <button key={platform} type="button" className="platform-choice" aria-pressed={selected.has(platform)} disabled={remote.busy} onClick={() => togglePlatform(platform)}>
                <i className="pd" style={{ backgroundColor: PLATFORM_COLORS[platform] }} />{PLATFORM_LABELS[platform]}<span className="check">{selected.has(platform) ? "✓" : ""}</span>
              </button>)}
            </div>
            <p className="collection-count">每个平台最多 100 条 · 同步只读取，不会修改平台收藏；取不到的部分会显示原因</p>
          </>
        )}
      </div>

      {library.error && <div className="status-line" role="alert"><AlertTriangle />{library.error}</div>}
      {tab === "remote" && remote.error && <div className="status-line" role="alert"><AlertTriangle />{errorMessage(remote.error)}<button type="button" className="text-link" onClick={onNavigateAccounts}>检查账号状态</button></div>}
      {tab === "remote" && data?.persistence_error && <div className="status-line" role="alert"><AlertTriangle />{data.persistence_error}</div>}

      {tab === "local" && library.migration && (
        <div className="status-line" role="alert">
          <AlertTriangle />
          <span className="status-message">
            检测到 {library.migration.count} 条旧版浏览器收藏（新版已改为保存在本机数据库）。迁移不会删除旧数据，备份文件仍可随时导出。
          </span>
          <button type="button" className="text-link" disabled={moving} onClick={() => void library.runMigration()}>迁移到本机收藏库</button>
          <button type="button" className="text-link" onClick={library.dismissMigration}>以后再说</button>
        </div>
      )}

      {tab === "local" ? (
        <div className="library-layout">
          <aside className="library-side" aria-label="收藏夹">
            <button
              type="button"
              className={`library-side-item ${selection.kind === "all" ? "active" : ""}`}
              onClick={() => setSelection({ kind: "all" })}
            >
              <Bookmark aria-hidden="true" />全部收藏<span>{library.items.length}</span>
            </button>
            <button
              type="button"
              className={`library-side-item ${selection.kind === "unclassified" ? "active" : ""}`}
              onClick={() => setSelection({ kind: "unclassified" })}
            >
              <FolderHeart aria-hidden="true" />未分类<span>{unclassifiedCount}</span>
            </button>

            <p className="library-side-title">收藏夹</p>
            {library.collections.map((collection) => (
              <div key={collection.id} className="library-side-row">
                {renaming === collection.id ? (
                  <span className="library-inline-form">
                    <input
                      className="field"
                      aria-label={`重命名收藏夹 ${collection.name}`}
                      value={renameValue}
                      autoFocus
                      maxLength={60}
                      onChange={(event) => setRenameValue(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") void submitRename(collection.id);
                        if (event.key === "Escape") setRenaming(null);
                      }}
                    />
                    <button type="button" className="icon-btn" aria-label="确认重命名" disabled={moving} onClick={() => void submitRename(collection.id)}><Check /></button>
                    <button type="button" className="icon-btn" aria-label="取消重命名" onClick={() => setRenaming(null)}><X /></button>
                  </span>
                ) : (
                  <>
                    <button
                      type="button"
                      className={`library-side-item ${selection.kind === "collection" && selection.id === collection.id ? "active" : ""}`}
                      onClick={() => setSelection({ kind: "collection", id: collection.id })}
                    >
                      <FolderHeart aria-hidden="true" /><span className="library-folder-name" title={collection.name}>{collection.name}</span><span className="library-folder-count">{collection.item_count}</span>
                    </button>
                    <button
                      type="button"
                      className="icon-btn library-side-action"
                      aria-label={`重命名收藏夹 ${collection.name}`}
                      onClick={() => { setRenaming(collection.id); setRenameValue(collection.name); }}
                    ><Pencil /></button>
                    <button
                      type="button"
                      className="icon-btn library-side-action"
                      aria-label={`删除收藏夹 ${collection.name}`}
                      onClick={() => void library.deleteCollection(collection.id)}
                    ><Trash2 /></button>
                  </>
                )}
              </div>
            ))}

            {creating ? (
              <span className="library-inline-form">
                <input
                  className="field"
                  aria-label="新收藏夹名称"
                  placeholder="收藏夹名称"
                  value={newName}
                  autoFocus
                  maxLength={60}
                  onChange={(event) => setNewName(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void submitNewCollection();
                    if (event.key === "Escape") { setCreating(false); setNewName(""); }
                  }}
                />
                <button type="button" className="icon-btn" aria-label="创建收藏夹" disabled={moving} onClick={() => void submitNewCollection()}><Check /></button>
                <button type="button" className="icon-btn" aria-label="取消创建" onClick={() => { setCreating(false); setNewName(""); }}><X /></button>
              </span>
            ) : (
              <button type="button" className="library-new" onClick={() => setCreating(true)}><FolderPlus aria-hidden="true" />新建收藏夹</button>
            )}
          </aside>

          <div className="library-main">
            {selectedKeys.length > 0 && (
              <div className="library-batch" role="status">
                <span>已选 {selectedItemKeys.length} 条</span>
                <label>
                  <span className="sr-only">加入收藏夹</span>
                  <select
                    className="field select"
                    aria-label="加入收藏夹"
                    value=""
                    disabled={moving || !library.collections.length}
                    onChange={(event) => { const id = Number(event.target.value); if (id) void batchAdd(id); }}
                  >
                    <option value="">{library.collections.length ? "加入收藏夹…" : "先新建一个收藏夹"}</option>
                    {library.collections.map((collection) => <option key={collection.id} value={collection.id}>{collection.name}</option>)}
                  </select>
                </label>
                {activeCollection && (
                  <button type="button" className="btn" disabled={moving} onClick={() => void batchRemove(activeCollection.id)}>
                    移出「{activeCollection.name}」
                  </button>
                )}
              </div>
            )}

            {library.loading && !library.items.length ? (
              <div className="empty" role="status"><div className="empty-symbol"><Loader2 className="spinner" /></div><h2>正在读取本机收藏</h2><p>收藏保存在本机数据库，清缓存或换浏览器都不会丢。</p></div>
            ) : localResults.length ? (
              /* key 里带上当前收藏夹：切换时强制重挂载，内部勾选/筛选/平台页签一并重置，
                 避免上一个收藏夹里勾选的内容泄漏到下一个视图的批量操作里 */
              <ResultTabs
                key={`${selection.kind}-${selection.kind === "collection" ? selection.id : "all"}`}
                results={localResults}
                overall="completed"
                platforms={PLATFORMS}
                library={library}
                savedView
                jobId="bookmarks"
                onSelectionChange={setSelectedKeys}
                selectionToolLabel="批量管理"
                selectionResetKey={selectionResetKey}
              />
            ) : (
              <div className="empty">
                <div className="empty-symbol"><Bookmark /></div>
                <h2>{activeCollection ? "这个收藏夹还是空的" : selection.kind === "unclassified" ? "没有未分类的内容" : "收藏夹还空着"}</h2>
                <p>{activeCollection ? "在「全部收藏」里勾选内容，再选择「加入收藏夹」。另：同一条内容可以同时属于多个收藏夹。" : "遇到值得再读的内容，点一下结果右侧的收藏图标。"}</p>
              </div>
            )}
          </div>
        </div>
      ) : remote.busy && !data?.results.length ? (
        <div className="empty" role="status"><div className="empty-symbol"><Loader2 className="spinner" /></div><h2>正在整理你的收藏</h2><p>先获取列表，再补充内容信息。</p></div>
      ) : data ? (
        <>
          <p className="collection-count">本机已保存 {data.results.length} 条 · 每次最多更新各平台最新 100 条，未取到的旧内容保留</p>
          <div className="progress-strip" aria-live="polite">
            {Object.entries(data.platforms).map(([platform, info]) => info && <span key={platform} className="progress-item">
              {PLATFORM_LABELS[platform as PlatformSlug]}：{info.status === "running" ? "同步中" : STATUS_LABELS[info.status]} · 本次 {info.result_count} 条
              {info.synced_at && <small>同步于 {new Date(info.synced_at).toLocaleString("zh-CN")}</small>}
            </span>)}
          </div>
          {!remote.busy && Object.values(data.platforms).some(info => info?.status === "cancelled") && <p className="collection-count" role="status">同步已取消，已获取的内容和历史收藏仍会保留。</p>}
          {Object.entries(data.platforms).some(([, info]) => info && !["succeeded", "empty", "running", "pending", "cancelled"].includes(info.status)) && <div className="status-line"><span className="status-message"><AlertTriangle />部分平台没有完成：{Object.entries(data.platforms).filter(([, info]) => info && !["succeeded", "empty", "running", "pending", "cancelled"].includes(info.status)).map(([platform, info]) => `${PLATFORM_LABELS[platform as PlatformSlug]} ${info?.error_summary || STATUS_LABELS[info!.status]}`).join("；")}</span><button type="button" className="text-link" onClick={onNavigateAccounts}>检查账号</button></div>}
          <ResultTabs results={data.results} overall={data.overall} jobId={data.job_id} platforms={Object.keys(data.platforms) as PlatformSlug[]} library={library} fetchedAt={fetchedAt} />
        </>
      ) : (
        <div className="empty"><div className="empty-symbol"><FolderHeart /></div><h2>把喜欢的内容，放到一起</h2><p>选择平台后点击同步，四处散落的收藏会汇到这里。</p><button type="button" className="btn" onClick={() => void remote.sync([...selected])}>同步收藏</button></div>
      )}
    </div>
  );
}
