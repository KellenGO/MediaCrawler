# 仓库目录与日常入口

日常测试使用 `dist/SiYe/四野.exe`，根目录 `MediaCrawler.bat` 优先打开它；`SiYe.exe` 是托盘和工作进程使用的后端程序。`启动-源码.bat` 是独立的源码开发入口，默认 8090；直接运行 `scripts/start.ps1` 默认 8080。多工作区开发用 `SIYE_PORT` 显式区分端口。

| 位置 | 放什么 |
| --- | --- |
| `api/`、`aggregate_search/`、`media_platform/` | API、任务编排与平台实现；本轮保持模块位置，避免整理破坏导入 |
| `base/`、`config/`、`tools/` 等 Python 目录 | 公共运行支持与原有依赖；不要仅凭目录名判断无用 |
| `webui/src/`、`webui/tests/` | 应用前端和测试 |
| `browser_extension/` | 可选浏览器登录同步扩展 |
| `assets/` | 程序图标等发布资源 |
| `site/` | 对外介绍页与使用指南 |
| `style-preview/` | UI 参考稿，保留供设计对照，不是运行入口 |
| `scripts/`、`tests/` | 可重复执行的构建、诊断与测试；一次性代码编辑脚本不保留在前端目录 |
| `docs/features/` | 当前功能 wiki |
| `docs/decisions/`、`docs/history/` | 取舍与历史记录，历史记录不代表当前验收状态 |
| `.workbuddy/memory/` | 按日追加的本机流水账 |
| `build/`、`dist/`、`.tmp_pytest_*/` | 可重建的构建、运行及测试产物；不要提交 |
| `data/`、`browser_data/`、`.cache/` | 用户收藏、登录资料及缓存；不能当作普通构建垃圾清理 |

源码运行和 EXE 运行的数据目录不同。旧测试包资料保存在根目录 `data/version-backups/`，未自动合并数据库；发布包必须从干净目录构建，不能把日常使用后的 dist 直接上传。

保留另一个 worktree 和分支作历史参考，不作为主入口，不删除其未提交交接文档。合并后继续开发应从最新 master 开始。
