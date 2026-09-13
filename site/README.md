# 四野 · 推广落地页

`site/` 是给外部访问者看的单页落地页（介绍 + 下载），和 `webui/` 里那个本地 App 是两件事：

| | `webui/`（App） | `site/`（落地页） |
| --- | --- | --- |
| 给谁看 | 已经装好并在本机运行的用户 | 还没下载、第一次听说项目的人 |
| 怎么跑 | 需要 FastAPI 后端 + `webui/dist` | 单个 HTML 文件，双击就能看 |
| 依赖 | React / Vite / Node.js | 无。可离线打开，也可直接丢到任何静态托管 |

页面是**单文件**：CSS、JavaScript、图标、界面示意图全部内联，没有构建步骤，也没有必须联网才能加载的资源。

## 本地预览

直接双击 `site/index.html`，或者：

```shell
# 想要一个 http 地址（例如测试手机访问）
python -m http.server 8811 --directory site
```

## 上线

### 方式一：GitHub Pages（推荐，已配好）

仓库里已经有 `.github/workflows/pages.yml`：push 到 `master` 且改动了 `site/` 时会自动发布。

首次使用要做一次设置：

1. 打开仓库 **Settings → Pages**；
2. 把 **Source** 从 `Deploy from a branch` 改成 **`GitHub Actions`**；
3. 到 **Actions** 页面手动跑一次 `Deploy landing page to GitHub Pages`，或者往 `site/` 提交任意改动。

发布后的地址默认是 `https://kellengo.github.io/MediaCrawler/`。

### 方式二：任何静态托管

`site/index.html` 一个文件就能用，也可以整个 `site/` 目录丢上去：Cloudflare Pages、Vercel、Netlify、对象存储、自己的服务器都行。没有构建命令，输出目录就是 `site`。

### 方式三：不进浏览器也能发

文件是自包含的，直接把这个 HTML 发给别人也能打开（对方本地双击即可）。注意这种用法下站外链接仍然需要联网。

## 上线前要改的几处

页面里有两处刻意留的占位（域名和 Release），推广前建议处理掉：

1. **`canonical` / `og:url`**（`<head>` 里）现在写的是 `https://kellengo.github.io/MediaCrawler/`。如果你用自定义域名或别的托管地址，改成真实地址，否则分享卡片和搜索引擎会认错。
2. **`og:image`** 已经生成了：`site/og.png`（1200×630，页面首屏的截图）。它和 `canonical` 一样写死在 meta 里指向 `https://kellengo.github.io/MediaCrawler/og.png`，换域名时记得一起改。想换图就替换 `site/og.png`（保持 1200×630）；改了页面文案后重新生成用：

   ```shell
   uv run python scripts/build_landing_og.py
   ```
3. **下载按钮**指向 `https://github.com/KellenGO/MediaCrawler/releases/latest`。仓库现在还没有 Release，建议推广前先建一个（下面有步骤），否则访问者点进去看到的是空页面。
4. **首屏界面示意图**是纯 CSS 画的。换成真实截图更有说服力，见下一节。

### 换成真实截图

首屏那张结果是**纯 HTML/CSS 复刻的新版结果页**（搜索框、平台进度条、Tabs、编号结果行都与真实界面同一套样式），不依赖任何图片。

换真图的方法：在 `site/index.html` 里搜 `界面示意`，把 `<div class="mock" ...>...</div>` 整块删掉，替换成：

```html
<img src="shot-search.png" alt="四野 搜索结果页：小红书、抖音、B站、知乎 结果合并展示"
     style="width:100%;border:1px solid var(--line);border-radius:16px;box-shadow:var(--shadow)">
```

下面那行 `.mock-cap`（图注）可以保留。截图建议：1440 或 1600 宽、浅色主题、搜索关键词与示例一致（现在是「露营装备」）、能看到平台进度条和 3–4 条结果。图片放进 `site/` 目录用相对路径引用，别用图床外链。改完记得重新生成 `og.png`。

### 改文案 / 改配色

- 所有文案都是页面里的中文纯文本，直接改，不涉及模板语法。
- **配色与字体对齐当前 App**，来源是 `webui/src/index.css` 和视觉稿 `style-preview/9-full-preview.html`：
  纯白底（深色 `#101219`）、发丝细线、单一靛蓝强调色 `#6573ff`（深色 `#8b95ff`），**没有毛玻璃、没有光斑渐变**。
  落地页把同一套 token 写在 `<style>` 顶部的 `:root` 里，改 `--brand` / `--brand-soft` 就能整体换色，深色在 `html.dark` 里。
- 字标「四野」下方那条渐变条是品牌标记，`--grad: linear-gradient(90deg,#6677fb,#29ddcc)`，和 App 的 `.home-wordmark::after`
  以及网站图标用的是同一组颜色；改色请三处一起改（`site/index.html`、`webui/src/index.css`、`public/favicon`）。
- 字体用 `"Segoe UI Variable Text","Segoe UI","Microsoft YaHei",system-ui`（与 App 一致），**页面不引用任何外部字体或图片**，
  整个 HTML 零外部请求，断网也能完整显示。深色模式默认跟随系统，右上角按钮可手动切换并记住选择。

## 先把 Release 建出来

落地页的下载按钮需要有东西可下：

1. 到仓库 **Actions → Windows Executable Release → Run workflow**（或推一个 `v*` 标签，例如 `v0.1.0`）；
2. 工作流会跑后端测试、前端测试、构建前端、打包 EXE，并在 clean-room 里解压验证；
3. 跑完后下载 artifact `MediaCrawler-Windows-x64`，里面是 `MediaCrawler-Windows-x64.zip` 和 `.sha256`；
4. 到 **Releases → Draft a new release**，建一个 tag（和 workflow 里读到的 `pyproject.toml` 版本一致最省事），把上面两个文件传上去，写几句更新说明再发布。

发布后 `releases/latest` 就会自动指向它，落地页不需要再改。

## 可粘贴的推广文案

都是根据 README 里的实际能力写的，没有超出项目现状的说法。用之前按平台习惯删改。

**一句话版**

> 四野：一次搜索，同时看小红书、抖音、B站、知乎。四个平台结果合成一个页面，统一排序、跨平台去重，能筛选、收藏、导出。Windows 免安装，本机运行，数据不出电脑。

**三段版（论坛 / 群公告 / 公众号开头）**

> 找一个主题，以前要分别打开小红书、抖音、B站、知乎搜四遍，再自己来回对比，同一条内容还得靠眼睛认出来。
>
> 四野把这四个平台的搜索结果收进同一个结果页：并行搜索（单个平台失败不影响其他平台）、统一结果模型、综合 / 最新 / 互动最多三种排序、跨平台去重分组，之后还能按时间、类型、关键词筛选，收藏写备注，导出 CSV / Markdown 或批量复制链接。
>
> 全部在本机跑，后端只监听 127.0.0.1:8080，账号 profile 和收藏都不上传。开源，非商业许可。下载：[链接]

**技术向（V2EX / 少数派 / 掘金这类）**

> 开源了一个跨平台中文内容聚合搜索工具：把小红书、抖音、B站、知乎的搜索结果归一化成同一套 `UnifiedSearchResult`，再统一做排序、snippet 摘要、后台补全、编辑距离去重与分组。
>
> 后端 FastAPI + Playwright，四个平台跑在隔离的 worker 进程里，由 supervisor 管；搜索前有一次完全本地的登录预检（约 1ms，不启动浏览器就能判断哪些平台搜不了）；结果缓存 90 秒，明确限流后按 60/120/240/300 秒冷却，最近 100 次搜索的成功率、缓存命中率、P95 都有统计。
>
> 前端 React + Vite，Windows 免安装包内置 Python runtime。本机运行，数据不出电脑。非商业许可（fork 自 NanmiCoder/MediaCrawler）。

**发之前提醒自己**

- 页面和文案都要写明**非商业许可**（NON-COMMERCIAL LEARNING LICENSE 1.1），别写成「随便用」。
- 别说成「爬虫工具」或强调批量采集，这个仓库的产品主体是聚合搜索；README 也是这么定位的。
- 建议在推广帖里放一张真实结果页截图，转化差别很大。
- 平台风控和字段变化是已知情况，别承诺「稳定」「永远不会失效」。被问到结果不全时，可以直接引用页面的 FAQ 部分。

## 自检清单

- [ ] `site/index.html` 双击能打开，浅色 / 深色都正常，手机上不横向滚动
- [ ] 首屏「下载」按钮真的能下到 zip（Release 已发布）
- [ ] `canonical` / `og:url` 换成了真实地址
- [ ] 至少替换了首屏界面图为真实截图
- [ ] 分享链接到微信 / 群里，看一眼卡片标题和描述
