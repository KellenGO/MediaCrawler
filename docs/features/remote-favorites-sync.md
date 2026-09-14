# 跨平台收藏同步（拉取 + 持久化）

## 一句话

把四个平台「已收藏」的内容拉下来并落库到本机 SQLite（原来只存在进程内存里、重启即丢），
每个平台单次上限 **100 条（默认 20）**，按平台允许的分页方式逐页读取。

## 代码入口

| 职责 | 位置 |
|---|---|
| 持久化（表 `remote_favorites` / `remote_sync_runs`） | `api/services/remote_favorites_store.py` |
| 任务编排、逐平台落库、错误 drain | `api/services/favorites_job_manager.py`（`FavoritesJobManager`） |
| HTTP 路由（前缀 `/api/search`） | `api/routers/search.py`：`POST /favorites/jobs`、`GET /favorites/jobs/latest`、`GET /favorites/jobs/{job_id}`、`POST /favorites/jobs/{job_id}/cancel` |
| 请求 / 响应模型（`limit_per_platform` 默认 20、上限 100） | `api/schemas/favorites.py` |
| 抓取侧（超时、分页、错误码） | `aggregate_search/worker.py` + 各平台 `media_platform/*/core.py` |
| 前端 | `webui/src/hooks/useFavorites.ts` |

数据文件：与收藏库**同一个** `data/library.db`。

## 关键决定

- **逐平台落库**：某平台失败 / 限流，不影响其他平台已保存的数据。
- 按 `(account_key, platform, content_id)` 去重合并（`ON CONFLICT DO UPDATE`）。
- **本次没取到的旧条目一律不删** ——「这次没出现」≠「用户取消了收藏」。
- 打开页面**只显示上次保存的数据和同步时间，不自动访问平台**；只有用户主动点同步才更新。
- 遇限流 / 验证码 / 登录失效就停止该平台，保存已取内容并显示原因；**不自动重试、不降数量试探**。
- 取消 / 中断的同步落库为 `cancelled`，**不写 `running`**（否则前端会一直转圈）。
- 子进程 stderr 用并发任务**持续 drain**，避免日志塞满管道把进程卡死。
- 同步进行中或失败时仍展示本机旧内容；磁盘写入失败会单独提示，不能把“这次看到了”当成“已经保存”。
- 重启后仍保留互动数据的近似值标记，避免给旧快照制造虚假的精确度。
- 同步期间可点击「取消同步」：停止当前任务所有尚未完成的平台，等待保存已返回的内容后恢复同步入口。不会删除历史收藏，也不会撤销已完成平台的结果；取消请求失败时保留重试入口。
- 「取消同步」直接替换原同步按钮，显示在同一位置；创建任务尚未返回时短暂显示「正在启动同步」，避免用户寻找另一个按钮。

## 已知坑 / 边界

- **账号隔离没接**：`load()` 与 `save_platform()` 都没传 `account_key`，实际恒为 `"default"`，
  而存储层注释写着「不同账号分开保存」。**换账号同步会合并进同一份本机归档**，
  不要对外宣传为多账号隔离。
- 尚未用真实账号实测四个平台；**不能承诺每个平台一定返回 100 条**，当前也不是全量同步。
- `limit_per_platform` 只放宽了**收藏同步**；搜索结果那个 40 条上限没动。
- bilibili / 知乎的「读到 100」目前只有人工审查，**缺自动化测试**。
- 缺「落库 → 重启 → `latest()` 还原」的集成测试（现有覆盖靠 store 单测 + 桩）。

## 测试怎么跑

`tests/test_remote_favorites_store.py`、`tests/test_remote_favorites.py`、`tests/test_favorites_reliability.py`
