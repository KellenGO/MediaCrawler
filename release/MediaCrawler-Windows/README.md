# MediaCrawler

## 中文社交平台聚合搜索

一次搜索小红书、抖音、Bilibili 和知乎，将分散在不同平台的中文内容统一检索、排序和展示。

本项目的产品主体是跨平台搜索，而不是通用爬虫控制台。

## 产品截图

<!-- 截图位置：待补充当前聚合搜索页面截图。 -->

## 为什么做这个项目

查找一个主题时，用户通常要分别打开小红书、抖音、Bilibili 和知乎，重复搜索并手动比较结果。

本项目希望把：

```text
四个平台 × 四次搜索
```

变成：

```text
一次搜索 → 一个结果页
```

## 核心功能

- 四个平台并行搜索，单个平台失败、超时或取消时仍可返回其他平台的结果。
- 支持部分结果返回、单平台重试，以及受控的 Provider fallback。
- 使用统一的 `UnifiedSearchResult` 表达标题、snippet、作者、发布时间、封面和互动数据。
- “综合”排序结合关键词相关性、平台原始 rank、新鲜度、平台内互动表现和平台多样性。
- “最新”排序与“互动最多”排序；互动排序中评论、收藏、投币、分享等深度互动权重大于播放量。
- snippet 搜索摘要；对缺少有效摘要的前排结果，支持不阻塞首屏的 Result Hydration 补全。
- 跨平台内容去重与 Content Grouping：同一内容可以合并为一张主卡片，同时保留各平台入口。
- 90 秒短期内存结果缓存，支持账号状态变化失效和 `bypass_cache` 强制重新搜索。
- 账号、Cookie/Session 与 persistent browser profile 管理。
- Platform Doctor：在账号设置中查看搜索可用性、当前搜索路径、fallback 和简介能力。
- worker 隔离与常驻 supervisor，降低平台请求之间的相互影响。

## 支持平台

当前聚合搜索正式支持：

| 平台 | 聚合搜索 |
| --- | --- |
| 小红书 | ✅ |
| 抖音 | ✅ |
| Bilibili | ✅ |
| 知乎 | ✅ |

表格之外的平台不属于当前聚合搜索的正式支持范围。

## 搜索流程

```text
Keyword
   ↓
┌────────┬──────┬──────────┬──────┐
│ 小红书 │ 抖音 │ Bilibili │ 知乎 │
└────────┴──────┴──────────┴──────┘
   ↓
Provider chain / platform workers
   ↓
Unified Results
   ↓
Snippet / Hydration / Grouping / Dedup / Ranking
   ↓
Search UI
```

## 快速开始

### 环境要求

- Python 3.11
- [uv](https://docs.astral.sh/uv/)
- Node.js 20 或兼容的 LTS 版本（仅构建前端或运行开发服务器需要）
- 可用的 Chrome/Chromium 浏览器

### 普通用户：下载 Windows Release 包

从 GitHub Releases 下载 `MediaCrawler-Windows.zip`，解压后先准备 Python 3.11+ 环境并在解压目录执行 `uv sync --no-dev`，然后双击 `MediaCrawler.bat`。Release 包已经包含 `webui/dist`，日常运行不需要 Node.js、npm 或前端源码。

### 安装 Python 依赖

在仓库根目录执行：

```shell
uv sync
```

如果使用项目管理的 Playwright Chromium，首次使用时安装浏览器：

```shell
uv run playwright install chromium
```

项目也支持按现有配置使用本机浏览器或 CDP。

### Windows 一键启动（推荐）

在仓库根目录双击 `MediaCrawler.bat`。启动器会检查 Python、Python 依赖和前端构建文件，然后启动 FastAPI 后端，等待 `/api/health` ready，最后打开系统默认浏览器。普通使用不需要 Node.js，也不会启动 Vite dev server。

如果找不到 `webui/dist`，请先按下方开发者步骤执行 `npm ci` 和 `npm run build`；不会自动安装 Python 或 Node.js。启动器不会使用 `--reload`，也不会终止其他程序占用的端口。

启动窗口中按 `Ctrl+C` 会清理本次由启动器创建的后端进程。已运行的 MediaCrawler 服务会直接复用，不会重复启动。浏览器或其他本地环境检查出现 warning 时，页面仍会打开，具体状态可在应用中查看。

### 启动后端

在仓库根目录执行：

```shell
uv run uvicorn api.main:app --host 127.0.0.1 --port 8080 --reload
```

API 地址为 `http://127.0.0.1:8080`。完成前端生产构建后，后端也会直接提供构建后的页面。

### 前端开发环境

另开终端：

```shell
cd webui
npm ci
npm run dev
```

开发页面通常位于 `http://localhost:5173`，开发服务器会将 `/api` 请求代理到后端。

### 构建生产前端

```shell
cd webui
npm ci
npm run build
```

构建产物输出到 `webui/dist/`。随后启动后端并访问 `http://127.0.0.1:8080` 即可使用。

源码仓库不提交 `webui/dist`；GitHub Actions 的 release package workflow 会在构建后把它装入 `MediaCrawler-Windows.zip`。

## 账号同步

部分平台在搜索、详情接口或访问频率方面需要有效的浏览器会话。账号设置页可以查看四个平台的账号状态，并通过 browser extension 同步当前浏览器中的 Cookie/Session 到项目使用的隔离 profile。

账号状态不等同于搜索能力：例如账号尚未完成 API 验证时，平台仍可能通过浏览器备用路径完成公开搜索。Platform Doctor 会分别展示账号状态、搜索路径和简介能力。

请只同步和使用你有权使用的账号及登录状态，并遵守目标平台的服务条款。

## 项目架构

```text
Web UI / Browser Extension
            ↓
        FastAPI API
            ↓
      Search Job Manager
            ↓
  Worker Supervisor / isolated workers
            ↓
      Provider Chain
            ↓
 XHS / Douyin / Bilibili / Zhihu
            ↓
   Adapter → UnifiedSearchResult
            ↓
 Hydration / Grouping / Dedup / Ranking / Cache
```

主要技术栈：

- Python 3.11
- FastAPI + Uvicorn
- React + Vite + TypeScript
- Playwright
- platform worker processes
- platform adapter layer
- search job manager、账号/session 服务和内存结果缓存

Provider fallback 只复用已有平台路径：小红书和 Bilibili 的轻量接口失败时可回退浏览器，知乎可回退页面路径；抖音当前使用已有的单一搜索路径。

## 测试

后端 fixture/unit tests：

```shell
python -m pytest -q tests/
```

前端搜索测试与生产构建：

```shell
cd webui
npm run test:search
npm run build
```

GitHub Actions 会在 push 或 Pull Request 到 `master` 时运行不依赖真实账号和真实平台网络的后端测试、前端搜索测试和 build。当前 ESLint 尚未作为完整配置的验收项。

## 已知限制

- 平台访问策略、登录要求和返回字段可能变化，搜索结果稳定性取决于平台当前状态。
- Result Hydration 是有限数量的后台补全，详情接口不可用时会保留初始结果。
- 跨平台去重和 Content Grouping 使用保守的标题、作者、时间和文本规则，不等同于语义理解。
- 分组主卡片默认使用代表结果的互动数据，不跨平台汇总互动量。
- Provider fallback 是串行且有界的，不会并行竞速或根据历史成功率自动择优。
- CI 不进行真实平台搜索；账号登录、浏览器 profile 和平台风控相关问题需要本地人工验证。

## Roadmap

- 继续调优搜索相关性和跨平台结果质量。
- 从去重分组进一步完善同内容的跨平台聚合。
- 优化搜索速度、冷启动和浏览器资源使用。
- 完善失败重试、账号同步和平台诊断体验。
- 根据实际需要评估更多平台接入。

## 与原 MediaCrawler 的关系

本项目基于 / fork 自 [NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)。感谢原作者提供底层多平台采集能力和项目基础。

当前仓库在其基础上开发并维护跨平台聚合搜索产品，包括统一结果模型、Provider Chain、排序、snippet、Hydration、跨平台去重与分组、缓存、账号状态和搜索 UI 等能力。上游更新会根据需要选择性吸收。

## License / Disclaimer

本项目保留 MediaCrawler 的 [NON-COMMERCIAL LEARNING LICENSE 1.1](LICENSE)。使用本项目之前请阅读许可证全文。

- 仅供学习、研究和非商业用途。
- 不得用于大规模抓取，或干扰、破坏目标平台的正常运营。
- 不得侵犯他人隐私、知识产权或其他合法权益。
- 不得用于任何违法或未经授权的用途。
- 商业使用必须遵循原许可证要求，并取得版权所有者的必要书面授权。

软件按“现状”提供，不提供明示或暗示的担保。使用者应自行遵守适用法律法规、目标平台服务条款及其他适用规则，并自行承担使用本项目产生的责任。

本 README 介绍的是当前仓库的聚合搜索产品。底层能力的来源、版权和许可限制仍以本仓库的 `LICENSE` 文件及 [上游仓库](https://github.com/NanmiCoder/MediaCrawler) 的 attribution 为准。
