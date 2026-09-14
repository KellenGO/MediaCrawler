# AGENTS.md — 先读这里

给所有在这个仓库里干活的 agent（人或 AI）的入口。**读完这一页，再去读 `docs/index.md`。**

## 这个项目是什么

「四野」：本地运行的中文社交平台聚合搜索工具。FastAPI 后端（`api/`）+ React 前端（`webui/`）
+ Playwright 抓取（`aggregate_search/`、`media_platform/`）。只监听 `127.0.0.1:8080`，
用使用者本人的登录态去搜小红书 / 抖音 / B站 / 知乎。打包成两个 EXE 分发。

## 知识库怎么用（两层，别搞混）

| 层 | 位置 | 性质 | 写什么 |
|---|---|---|---|
| 流水账 | `.workbuddy/memory/YYYY-MM-DD.md` | 按天、只追加 | 今天做了什么、踩了什么坑 |
| 功能 wiki | `docs/features/*.md` | 按功能、持续更新 | 这个功能是什么、入口在哪、为什么这样做、边界在哪 |

- 想了解某个功能，**读 `docs/features/<功能>.md`**，不要靠翻流水账。
- **一个功能一个文件**：改功能时顺手更新对应那一份。
- **别在 wiki 里复述代码**（签名、字段表、配置项一律不写）——只写从代码里读不出来的东西。
- 重要的取舍写进 `docs/decisions/`。

## 完成定义（DoD）——说"干完了"之前逐条过

改完任何功能，**在把任务标记为完成之前**必须满足：

- [ ] 相关测试通过（后端 `pytest --basetemp=.tmp_pytest_xxx`；前端 tsc + 测试）。
- [ ] **更新 `docs/features/<功能>.md`**：入口变了改「代码入口」，做法变了改「关键决定」，
      修掉或新发现的坑改「已知坑 / 边界」。
      （纯内部重构、对外行为没变就跳过——别为了改而改。）
- [ ] 做了取舍 → 在 `docs/decisions/` 加一条（背景 / 选项 / 决定 / 后果 + 状态），
      格式照 `docs/decisions/2026-09-14-登录方式取舍.md`。
- [ ] 加了新功能 → 在 `docs/index.md` 加一行，并按 `docs/features/_TEMPLATE.md` 新建一份。
- [ ] 在 `.workbuddy/memory/YYYY-MM-DD.md` 追加当天的流水账（按日期，只追加）。

`tests/test_docs_wiki.py` 会守住**结构**（索引链接、必备小节、地图与文件一一对应）。
它**不检查内容是否写对**——内容准确性只能靠 agent 自觉，所以上面这份清单是**收尾动作，不是建议**。

## 硬规则

- **绝不提交 `data/`、`browser_data/`**：`data/` 是本机收藏库与日志，`browser_data/` 是各平台登录
  profile（**含 cookie**）。发布包必须排除，`scripts/package_exe.py` 会校验并拒绝。
- 需要写库的测试一律用临时目录，别碰真实用户数据。

## 在这台机器上干活（环境坑，都踩过了）

- **npm 被安全策略拦**（会拉起 wsl.exe）。前端改用 node 绝对路径：
  `node_modules/typescript/bin/tsc`、`node_modules/vite/bin/vite.js`、`node run-compiled-tests.mjs`。
- **pytest 写不进系统 Temp**，必须带项目内临时目录：`--basetemp=.tmp_pytest_xxx`。
- **shell 会 mangle 带斜杠的参数**：`git branch feat/x` 会静默失败并报 `fatal: invalid reference`。
  git 操作走 PowerShell，分支名用连字符。
- Python 用 `.venv/Scripts/python.exe`（该 venv 由 uv 建，原本没有 pip）。

## 当前分工（截至 2026-09-14，会过期）

| 位置 | 分支 | 负责 | 内容 |
|---|---|---|---|
| `MediaCrawler-main/` | `master` | 一个 agent | 本地收藏夹 / 跨平台同步持久化 / 托盘启动 |
| `MediaCrawler-scanlogin/`（git worktree） | `feat-scan-login` | 另一个 agent | 方案 A：扫码登录升为主路径，扩展降级 |

两个目录**共用一个 `.git`**，不需要 push/pull；合并前各自先提交，合并时只需处理 `docs/` 与 `site/` 的文档冲突。
