# 本地收藏夹

## 一句话

用户收藏从浏览器 `localStorage` 迁到本机 SQLite，支持把**一条内容分到多个收藏夹**（多对多）。

## 代码入口

| 职责 | 位置 |
|---|---|
| 存储层（表 `items` / `collections` / `item_collections`） | `api/services/library_store.py`（`LibraryStore`，依赖注入 `get_library_store`） |
| 旧格式互动数据 / 元信息兼容编解码 | `api/services/favorite_snapshot.py` |
| 请求 / 响应模型 | `api/schemas/library.py` |
| HTTP 路由（14 个，前缀 `/api/library`） | `api/routers/library.py`，在 `api/main.py` 注册 |
| 前端 API 层（纯函数 + axios 两段） | `webui/src/lib/libraryApi.ts` |
| 前端状态与写操作 | `webui/src/hooks/useBookmarks.ts` |
| 收藏夹界面（左列表 / 右结果） | `webui/src/components/favorites/FavoritesPage.tsx` |
| 备份导出 / 导入 | `webui/src/components/search/BookmarkBackup.tsx` |

数据文件：`data/library.db`（`base/runtime_paths.writable_path()`；源码模式 = 项目根，打包后 = EXE 同级）。

## 关键决定

- **一条内容可属于多个收藏夹，底层只存一份**：`UNIQUE(platform, content_id)` + 关联表。
- 「未分类」是**虚拟视图**（不属于任何收藏夹），不占实体行。
- 自建收藏夹与「全部收藏／未分类」用标题、细分隔线和短蓝线区分；编辑、删除使用统一小号线性图标，键盘聚焦和触屏下也可操作。
- **删除收藏夹默认保留内容**，只解除归属；「取消收藏」是独立接口，避免误删。
- 重复收藏只刷新内容快照，**保留首次收藏时间与已有备注**；改备注只能走 `PATCH`。
- 沿用既有前端限制：备注 1000 字、总量 500 条。
- 旧 `localStorage` 收藏**只提示、不自动删**；迁移有跳过项时**不写**完成标记（否则用户失去迁移入口）。
- 并发重复收藏用 `INSERT OR IGNORE` + 冲突退化为更新（幂等），避免撞 UNIQUE 直接 500。
- 多个页面共享收藏状态；备注以实际写入成功为准，失败时保留草稿，方便直接重试。
- 导入结构出错时回滚整次操作；条目无效或超出容量则按实际跳过数量反馈，避免误报全部成功。

## 已知坑 / 边界

- `PATCH /items/{platform}/{content_id}` 把 content_id 放**路径参数**：含 `/` 的 ID 会被切段，
  可能改错条目或 404。当前数据无此情况，其他接口都走 body。
- 500 条上限在批量导入时按实际条目数判定，超限条目被跳过并反馈。
- 本地库**缺并发/锁测试**；长导入是单条 `BEGIN IMMEDIATE` 事务，并发写超过 10s 会超时。
- 传了已删除的 collection_id 会让该条内容**整条**收藏失败（单条 400，批量静默跳过）。
- 备注超 1000 字是**静默截断**，不给用户提示。

## 测试怎么跑

- 后端：`tests/test_library_store.py`、`tests/test_library_api.py`
- 前端：`webui/tests/libraryApi.test.ts`、`webui/tests/resultLibrary.test.ts`
- 跑法（`--basetemp`、node 绝对路径）见根目录 `AGENTS.md`。
