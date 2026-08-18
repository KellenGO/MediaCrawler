# MediaCrawler

## 中文社交平台聚合搜索

输入一次关键词，同时搜索小红书、抖音、B 站和知乎，把分散在不同平台的中文内容统一搜索、排序和展示。

本项目的产品主体是跨平台搜索。MediaCrawler 是底层数据采集基础和项目来源。

## 项目解决的问题

寻找一个主题时，用户通常需要分别打开小红书、B 站、抖音和知乎，重复进行四次搜索。

本项目希望把：

```text
四个平台 × 四次搜索
```

变成：

```text
一次搜索 → 一个结果页
```

## 核心功能

- 小红书、抖音、B 站、知乎并行搜索。
- 单个平台失败、超时或需要登录时，不拖垮其他平台；支持部分结果返回和单平台重试。
- 搜索任务取消、超时处理，以及隔离的 worker 和常驻 supervisor。
- 使用统一的 `UnifiedSearchResult` 展示不同平台的标题、摘要、作者、时间和互动数据。
- 基于 `title`、`snippet`、`author` 的关键词相关性计算。
- “综合”排序综合考虑关键词相关性、平台原始 rank、新鲜度、平台内互动表现和平台多样性。
- “最新”排序和“互动最多”排序；互动排序中评论等深度互动权重大于播放量。
- 统一 snippet 搜索摘要，跨平台内容去重，包括同一作者在多个平台发布的同一内容。
- 90 秒短期内存搜索缓存；账号状态变化自动失效，用户可通过“重新搜索”强制绕过缓存。
- 四个平台的账号状态、浏览器 Cookie / Session 同步，以及登录失效后的状态提示。

## 支持平台

当前的聚合搜索只接入以下四个平台：

| 平台 | 聚合搜索 |
| --- | --- |
| 小红书 | ✅ |
| 抖音 | ✅ |
| B 站 | ✅ |
| 知乎 | ✅ |

原始 MediaCrawler 还支持其他平台的数据采集，但微博、贴吧、快手等不代表已经接入本项目的聚合搜索。

## 搜索流程

```text
Keyword
   ↓
┌────────┬──────┬──────┬──────┐
│ 小红书 │ 抖音 │ B 站 │ 知乎 │
└────────┴──────┴──────┴──────┘
   ↓
Unified Results
   ↓
Snippet / Dedup / Ranking
   ↓
Search UI
```

## 快速开始

### 环境要求

- Python 3.11（仓库的 `.python-version`）
- [uv](https://docs.astral.sh/uv/)
- Node.js 20 或兼容的 LTS 版本
- 可用的 Chrome / Chromium 浏览器

### 安装 Python 依赖

```shell
uv sync
```

搜索或账号同步需要浏览器环境。项目可以使用本机浏览器或 CDP；如果使用标准 Playwright 浏览器且本机没有可用浏览器，可以执行：

```shell
uv run playwright install chromium
```

### 启动后端

在项目根目录执行：

```shell
uv run uvicorn api.main:app --port 8080 --reload
```

API 默认运行在 `http://localhost:8080`。

### 启动前端开发环境

另开一个终端：

```shell
cd webui
npm ci
npm run dev
```

前端开发地址通常是 `http://localhost:5173`，开发服务器会将 `/api` 请求代理到后端。

### 构建生产前端

```shell
cd webui
npm ci
npm run build
```

构建产物输出到 `api/webui/`。随后启动后端并访问 `http://localhost:8080`，API 会直接提供构建后的前端页面。

## 账号说明

不同平台对搜索接口、内容字段和访问频率的要求不同。部分场景需要登录状态才能获得更完整或更稳定的搜索结果；没有登录时，系统会尽量使用公开搜索，并在平台状态中说明限制。

账号页可以查看四个平台的验证状态，并将本地浏览器会话同步到项目管理的隔离 profile。账号状态变化会影响后续搜索缓存，并触发相应的失效处理。请只同步和使用你有权使用的账号及登录状态。

## 技术栈与架构

- Python 3.11
- FastAPI
- React + Vite + TypeScript
- Playwright / 本机浏览器或 CDP
- 平台 worker processes
- 平台 adapter layer
- search job manager、账号协调和内存结果缓存

搜索请求由 FastAPI 接收，search job manager 管理任务生命周期，再由各平台 worker 并行采集。adapter 将平台响应转换为统一结果，最后由聚合层完成 snippet、去重和排序，前端负责搜索交互与结果展示。

## 测试

后端测试：

```shell
python -m pytest -q tests/
```

前端搜索逻辑测试和生产构建：

```shell
cd webui
npm run test:search
npm run build
```

GitHub Actions 会在 push 或 Pull Request 到 `master` 时运行后端 fixture/unit tests、前端搜索测试和前端 build。CI 不使用真实账号、不登录平台，也不把真实平台搜索作为验收条件。ESLint 当前不是完整配置好的验收项，README 不将 lint 作为已完整支持的检查。

## Roadmap

- 继续调优搜索相关性。
- 从“删除重复”进一步发展为更好的跨平台内容聚合。
- 优化搜索速度和冷启动时间。
- 完善失败重试、登录状态和账号使用体验。
- 根据实际需要评估更多平台接入。

## 与 MediaCrawler 的关系

本项目基于 / fork 自 [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)。感谢原作者提供底层多平台采集能力和相关技术基础。

当前仓库在其基础上开发了跨平台聚合搜索产品，新增和维护搜索任务、统一结果模型、聚合排序、去重、缓存、账号状态和搜索 UI 等能力。

当前 `master` 与 upstream 历史没有 common ancestor，因此不承诺可以直接通过普通 rebase 或 merge 持续同步上游。后续将根据需要选择性吸收上游更新。

## License / Disclaimer

本项目沿用 MediaCrawler 的 [Non-Commercial Learning License](LICENSE)。使用前请阅读许可证全文。

- 仅供学习、研究和非商业用途。
- 不得用于大规模抓取、干扰或破坏平台服务。
- 不得侵犯他人隐私、知识产权或其他合法权益。
- 不得用于任何违法或未经授权的用途。
- 商业使用必须遵循原许可证要求，并取得必要的授权。

用户应自行遵守适用的法律法规、目标平台服务条款和 robots.txt 规则，并自行承担使用本项目产生的责任。项目作者不对因使用本项目造成的直接或间接损失承担责任。

本 README 只介绍当前仓库的聚合搜索产品；底层 MediaCrawler 的原始项目和许可证归属仍以其[上游仓库](https://github.com/NanmiCoder/MediaCrawler)及本仓库的 `LICENSE` 文件为准。
