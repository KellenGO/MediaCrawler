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
- 结果内筛选：按近 7 天 / 近 30 天、内容类型和关键词组合筛选，标题与摘要中的关键词高亮。
- 本地收藏与备注：保存内容快照和原文链接，刷新页面或重启后仍可查看。
- 支持将当前筛选结果或勾选结果导出为 CSV / Markdown，也可批量复制原文链接。
- snippet 搜索摘要；对缺少有效摘要的前排结果，支持不阻塞首屏的 Result Hydration 补全。
- 跨平台内容去重与 Content Grouping：同一内容可以合并为一张主卡片，同时保留各平台入口。
- 90 秒短期内存结果缓存，支持账号状态变化失效；`bypass_cache` 强制重新搜索，成功后更新缓存，失败时保留尚未过期的旧缓存。部分失败任务仅缓存已完整成功的平台。
- 账号、Cookie/Session 与 persistent browser profile 管理。
- Platform Doctor：在账号设置中查看搜索可用性、当前搜索路径、fallback 和简介能力。
- worker 隔离与常驻 supervisor，降低平台请求之间的相互影响。

### 筛选、收藏与导出

结果页的筛选只处理已经返回的内容，不会额外搜索平台。多个关键词用空格分隔，分别在标题、作者和摘要中匹配；时间范围按发布时间计算，日期未知的内容只在“全部时间”中显示。分组卡片按各来源独立判断条件，筛选后仅保留符合条件的来源。

点击卡片上方的“收藏”保存内容；分组卡片可一次收藏当前显示的全部来源。在搜索框下方点击“本地收藏”，无需重新搜索即可查看、筛选或取消收藏。备注编辑后需要点击“保存备注”。收藏保留保存时的内容快照，后续搜索不会覆盖已有备注或快照。

收藏保存在当前浏览器、当前网站地址的本地存储中，最多 500 个来源，每条备注最多 1000 字。更换浏览器、访问地址或清除网站数据前，请先导出留存；导出文件用于查看和整理，当前不支持导入恢复收藏。

未勾选时导出当前平台及筛选条件下的全部结果；勾选后仅导出选中结果。分组内容按来源分别导出，并按平台和内容 ID 去重。CSV 包含标题、作者、类型、发布时间、采集时间、收藏时间、备注、摘要和原文链接；使用 UTF-8 BOM 便于 Excel 识别中文。Markdown 适合整理阅读笔记。导出只包含已经保存的备注。

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

本项目有两种使用方式：普通用户使用 Windows 可执行包；开发者从源码运行。两种方式都使用同一个本地地址：`http://127.0.0.1:8080`。

### 普通用户：Windows 可执行包（推荐）

可执行包已经包含 Python runtime、FastAPI 后端和生产版 Web UI。普通使用不需要安装 Python、uv、Node.js、npm，也不需要手动运行 PowerShell 或 bat。

1. 下载 `MediaCrawler-Windows-x64.zip`（GitHub Actions artifact 或项目提供的 Release 包）；
2. 将 ZIP 解压到一个有写入权限的目录，不要只复制其中的 EXE；
3. 打开解压后的 `MediaCrawler` 文件夹，双击 `MediaCrawler.exe`；
4. 等待控制台显示 backend ready，程序会自动打开系统默认浏览器；
5. 在搜索框输入关键词，选择需要的平台后开始搜索。

程序默认监听 `127.0.0.1:8080`。运行期间不要删除 EXE 旁边的 `_internal`、`webui` 或其他运行文件。账号 profile、缓存和运行数据会在 EXE 所在目录附近创建，不会写入构建临时目录。

可执行包默认使用系统 Chrome/Edge；Windows 通常自带 Edge。如果 `/api/health` 显示浏览器不可用，请先安装或修复 Chrome/Edge，再重新启动。

### Windows 可执行包：账号同步

只有需要登录态、详情接口或更稳定平台访问时才需要同步账号。公开搜索不一定要求四个平台都登录。

1. 在 Chrome 或 Edge 中打开扩展管理页：Chrome 为 `chrome://extensions`，Edge 为 `edge://extensions`；
2. 打开“开发者模式”，选择“加载已解压的扩展程序”；
3. 选择 ZIP 解压目录中的 `MediaCrawler/browser_extension/`；
4. 在浏览器中登录小红书、抖音、Bilibili 或知乎；
5. 打开本地网站的“账号设置”，点击对应平台的“同步当前浏览器登录状态”；
6. 根据页面结果确认同步是否成功，然后返回搜索页使用。

扩展只向本机 MediaCrawler 后端同步必要的会话信息，不要把扩展目录或账号 profile 上传给他人。更详细的扩展说明见 [`browser_extension/README.md`](browser_extension/README.md)。

### 从源码运行：准备环境

源码运行需要：

- Python 3.11 或更高版本；
- [uv](https://docs.astral.sh/uv/)；
- Chrome/Edge，或可用的 Playwright Chromium；
- Node.js 20 或兼容的 LTS 版本（仅前端开发和构建需要）。

在仓库根目录安装 Python 依赖：

```shell
uv sync
```

如果使用项目管理的 Playwright Chromium，首次安装一次浏览器：

```shell
uv run playwright install chromium
```

### 从源码一键启动

确认已经存在 `webui/dist/index.html` 后，在仓库根目录双击：

```text
MediaCrawler.bat
```

启动器会检查 Python、依赖和前端构建文件，启动后端并轮询 `/api/health`。按 `Ctrl+C` 会清理本次启动的后端进程；如果 8080 已经是本项目服务，则直接复用，不会重复启动。

如果源码目录没有 `webui/dist`，先按下面的“前端开发与构建”步骤执行。启动器不会自动安装系统 Python 或 Node.js，也不会抢占其他程序正在使用的端口。

### 手动启动后端

在仓库根目录执行：

```shell
uv run uvicorn api.main:app --host 127.0.0.1 --port 8080 --reload
```

然后访问 `http://127.0.0.1:8080`。如果已经构建了 `webui/dist`，FastAPI 会直接提供生产版页面。

### 前端开发与构建

前端开发需要 Node.js：

```shell
cd webui
npm ci
npm run dev
```

开发页面通常位于 `http://localhost:5173`，Vite 会将 `/api` 请求代理到 `8080` 后端。修改 React/TypeScript 后可使用 HMR。

构建生产前端：

```shell
cd webui
npm ci
npm run build
```

构建产物输出到 `webui/dist/`。源码仓库不提交该目录；Windows executable workflow 会在构建后将它装入 `MediaCrawler-Windows-x64.zip`，并在 clean-room 中验证后上传 artifact。

筛选与收藏的逻辑测试包含在 `webui` 下的 `npm run test:search` 中。构建后，可在仓库根目录执行 `uv run python scripts/result_library_smoke.py` 验证真实浏览器操作；脚本默认使用系统 Edge、隔离浏览器存储和模拟 API，不会访问真实平台账号。使用已安装的 Playwright Chromium 时传入 `--channel chromium`。

### 常见启动问题

- **8080 端口被占用**：关闭占用该端口的本项目实例后再启动；程序不会强制终止其他应用，也不会自动改端口。
- **源码启动提示缺少 `webui/dist`**：进入 `webui` 执行 `npm ci` 和 `npm run build`。
- **页面可以打开但环境显示 degraded**：先查看账号设置中的 Platform Doctor；Redis、账号验证或浏览器状态异常不一定会阻止公开搜索。
- **搜索任务失败或结果不完整**：单个平台失败不会阻止其他平台返回结果，可在结果页对失败平台单独重试。
- **搜索结果显示“缓存”**：平台状态会显示原采集时间。点击“重新搜索”可获取最新结果；重复查看和后台摘要补全不会延长缓存有效期。

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
- 跨平台去重和 Content Grouping 在前后端使用一致的编辑距离和分组规则。相同或近似标题还需作者或有效摘要佐证；同名、发布时间接近不会单独触发合并。这仍是规则判断，不等同于语义理解。
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
