# Task Plan: 中文社交平台聚合搜索 MVP

## Goal
在 MediaCrawler 基础上构建一个 Windows 本机使用的"中文社交平台聚合搜索"网站，支持同时搜索小红书、抖音、Bilibili、知乎并统一展示结果。

## Current Phase
Phase 0 - 基线检查 (complete)

## Phases

### Phase 0: 基线检查
- [x] 检查 AGENTS.md (不存在)
- [x] 检查 .git (不存在)
- [x] 检查 Python (3.14.2 ✓)
- [x] 检查 uv (未安装 ⚠️)
- [x] 检查 Node.js (v24.15.0 ✓) 和 npm (11.12.1 ✓)
- [x] 验证关键代码路径 (全部存在)
- [x] 验证审计结论 (与代码一致)
- [x] 检查依赖安装状态 (Python 依赖和 node_modules 均未安装)
- **Status:** complete

### Phase 1: 统一模型与 Adapter
- [ ] 实现统一 DTO 模型 (models.py)
- [ ] 实现协议定义 (protocol.py)
- [ ] 实现基础 adapter (adapters/base.py)
- [ ] 实现四个平台 adapter (xhs/douyin/bilibili/zhihu)
- [ ] 编写 adapter 单元测试和脱敏测试
- [ ] 实现去重和交错排序逻辑
- **Status:** pending

### Phase 2: 核心薄 Hook
- [ ] 增加 CrawlerRuntimeOptions
- [ ] 编写默认行为兼容测试
- [ ] 增加 result_sink 机制
- [ ] 接入四个平台 core
- [ ] 确保普通 CLI 默认路径不变
- **Status:** pending

### Phase 3: 独立 Worker
- [ ] 实现 worker.py (stdin/stdout NDJSON 协议)
- [ ] 实现 login.py (单平台 login-only)
- [ ] 实现协议解析和 worker fake 测试
- [ ] 实现 cleanup、超时和错误分类
- **Status:** pending

### Phase 4: SearchJobManager 与 API
- [ ] 实现 SearchJobManager
- [ ] 实现 API schemas 和 routers
- [ ] 编写 fake worker 测试
- [ ] 验证四 worker 并行、单平台故障隔离、409 冲突
- [ ] 验证错误信息安全脱敏
- **Status:** pending

### Phase 5: 前端
- [ ] 实现搜索页、搜索栏、平台状态、标签筛选、结果卡片
- [ ] 保留原控制台入口
- [ ] TypeScript build 通过
- **Status:** pending

### Phase 6: 登录初始化与安全收尾
- [ ] 实现单平台 login-only 行为
- [ ] 禁止并发登录
- [ ] 修复 Cookie 日志泄漏
- [ ] 确认 API 监听 127.0.0.1
- **Status:** pending

### Phase 7: 验证
- [ ] 运行后端 pytest
- [ ] 运行前端 build
- [ ] 人工检查清单
- **Status:** pending

## Key Questions
1. uv 未安装 — 需改用 `sys.executable` 启动子进程 ✓ (已在设计中)
2. Python 依赖未安装 — 需 `pip install` 安装项目依赖
3. 前端 node_modules 未安装 — 需 `npm install`

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 使用 `sys.executable` 而非 `uv run python` | uv 未安装，且设计明确要求 |
| 每个平台独立 browser profile | 避免并发锁冲突 |
| 子进程通过 stdin/stdout NDJSON 通信 | 避免 Windows 命令行转义问题 |

## Notes
- 项目不是 git 仓库，无需 git 操作
- 现有 API 绑定 0.0.0.0，需改为 127.0.0.1
- 现有 crawler_manager.py 硬编码 `uv`，需修复
- 现有 CDP 模式默认开启，聚合搜索需关闭
