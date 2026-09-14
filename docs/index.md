# 功能地图

一行一个功能 → 详细文档 + 主要代码入口。**新增功能请在这里加一行。**
（项目背景、硬规则、环境坑见根目录 `AGENTS.md`。）

| 功能 | 文档 | 主要代码入口 |
|---|---|---|
| 本地收藏夹（收藏库 + 收藏夹分类） | [features/favorites-library.md](features/favorites-library.md) | `api/services/library_store.py`、`api/routers/library.py`、`webui/src/hooks/useBookmarks.ts` |
| 跨平台收藏同步 + 持久化 | [features/remote-favorites-sync.md](features/remote-favorites-sync.md) | `api/services/remote_favorites_store.py`、`api/services/favorites_job_manager.py` |
| 无窗口启动（托盘启动器） | [features/tray-launcher.md](features/tray-launcher.md) | `tray_main.py`、`MediaCrawler.spec` |
| 登录与账号（扩展 / 扫码 / profile） | [features/extension-login.md](features/extension-login.md) | `api/services/accounts.py`、`aggregate_search/worker.py` |

## 其他文档

- [`使用说明.md`](使用说明.md) —— 面向普通用户的操作步骤（网页版 `site/guide.html`）
- [`favorite-metrics.md`](favorite-metrics.md) —— 收藏指标补全的来源与字段
- [`三项功能审查与修复.md`](三项功能审查与修复.md) —— 2026-09-14 一轮修复的变更记录
- [`decisions/`](decisions/) —— 决策记录：为什么这么选

## 发布链路（与功能无关但常要用）

`scripts/build_exe.ps1` → `scripts/package_exe.py`（校验 + 打 zip）→ `scripts/exe_clean_room_smoke.py`
→ `.github/workflows/release-package.yml`。落地页与使用说明网页在 `site/`（GitHub Pages 自动部署）。
