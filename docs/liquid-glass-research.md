# Liquid Glass 开源实现调研（面向 webui：React 18 + Vite 6 + TS + Tailwind 3.4 + Radix）

> 调研时间：2026-09（本机 GitHub / npm registry / MDN / WebKit Bugzilla / web-platform-dx 实时查询）
> 结论先行：**真折射（SVG 位移）在 Web 上目前基本等于 Chromium-only**；你这个离线 Windows 工具绝大多数用户跑 Edge/Chrome，所以"真透镜"是可行的，但只能用在**极少数小面积元素**上，绝不能铺到结果列表。

---

## 0. 先看你现有工程已经有什么

已核实（读过源码，不是推测）：

- `webui/src/index.css:233-244` 已有 `.glass-panel` / `.glass-panel-dark`，用的是
  `backdrop-filter: blur(14px)` + `-webkit-backdrop-filter` + 1px 边框 + `--glass-bg` 变量（浅色 85%、暗色 72% 不透明度）。
- `webui/src/components/layout/Header.tsx:246` 顶部栏已是 `sticky top-0 z-20 bg-cyber-bg-primary/85 backdrop-blur-md`。
- 主题变量齐全：`--glass-bg / --glass-border / --glass-dark-bg / --glass-dark-border`，浅色 + `.dark` 两套（`index.css:80-84, 149-152`）。
- `webui/src/App.tsx:84` 已有一处 `glass-panel` 用法；`index.css:409` 已有 `.will-change-transform`。
- 启动方式：`desktop_main.py:80` 走 `webbrowser.open(BASE_URL)` → **用系统默认浏览器打开 localhost**，不是内嵌 WebView。所以渲染引擎取决于用户默认浏览器（Windows 上大概率 Edge=Chromium）。

**含义：你已经拥有"第 0 层"玻璃。升级到"真折射"是加一层，而不是重写。**

---

## 1. shuding/liquid-glass（Vercel 的 Shu Ding）

| 项 | 值 |
| --- | --- |
| URL | https://github.com/shuding/liquid-glass |
| Star | **1.2k**（GitHub API 实测 1158） |
| 许可证 | **MIT**（LICENSE 文件为 "MIT License / Copyright (c) 2025 Shu Ding"，已读原文） |
| 技术路线 | **SVG `feImage`（canvas 生成的位移贴图）+ `feDisplacementMap` + `backdrop-filter: url(#id)`** |
| React 集成难度 | **大**（本身不是组件，是 console 贴片） |
| 性能风险 | 高（见下） |
| 可访问性风险 | 中高 |

已核实的技术细节（读的是仓库里的 `liquid-glass.js` 源码，9397 字节）：

- 位移贴图不是 SVG 画的，是 **canvas 2D 实时生成**：`roundedRectSDF()` 算圆角矩形有符号距离场，逐像素算出 R/G 通道作为 X/Y 位移向量，再 `canvas.toDataURL()` 喂给 `<feImage>`。
- 滤镜通过 **`backdrop-filter: url(#${id}_filter) blur(0.25px) contrast(1.2) brightness(1.05) saturate(1.1)`** 作用到**元素背后的页面内容**上——这是它和"作用于自己子元素"方案的本质区别。
- 关键约束：`filterUnits="userSpaceOnUse"`、`colorInterpolationFilters="sRGB"` 是必需的（`sRGB` 不加会让 128 中性值漂移，整个背景偏移）。
- README 明说用法是"paste into any website console"——**没有 npm 包、没有 React 绑定、没有构建产物**。它是展示技术可行性的 demo，不是产品依赖。

### 它的 React 移植版：huozhi/vaso

| 项 | 值 |
| --- | --- |
| URL | https://github.com/huozhi/vaso ／ npm `vaso` |
| Star | **345** |
| 许可证 | GitHub 未标注 SPDX；README 写 "License: MIT" |
| 版本/时间 | 0.4.0，2025-08-03 发布（npm 实测） |
| 月下载 | 1,041（2026-08-13~09-11） |
| peer | 仅 `react` |
| React 集成难度 | **小**（`import { Vaso } from 'vaso'`，props: px/py/radius/depth/blur） |

注意：Vaso 是 shuding 实现的 React 化，API 形态是"渲染一层扭曲图层覆盖在 children 上"（`<Vaso depth={1.2} />`），**与 rdev 的 `backdrop-filter` 折射不是同一种东西**，观感更接近"放大镜/水波"而非"玻璃面板"。

---

## 2. rdev/liquid-glass-react

| 项 | 值 |
| --- | --- |
| URL | https://github.com/rdev/liquid-glass-react ／ npm `liquid-glass-react` |
| Star | **6.1k**（GitHub API 实测 6120，本类目最高） |
| 许可证 | **MIT**（package.json `"license": "MIT"`，已读原文） |
| 技术路线 | **SVG 位移滤镜（`feDisplacementMap`）+ `backdrop-filter`**，外加鼠标跟随的 elasticity / tilt |
| React 集成难度 | **小** |
| 性能风险 | **中高** |
| 可访问性风险 | 中（文字在 children 层，不受位移影响） |

已核实的可用性事实：

- **peerDependencies: `react: ">=18"`, `react-dom: ">=18"`**（读原始 package.json）→ **你的 React 18.3.1 可以直接装，不需要升级到 19**。这是它比很多新库（要求 React 19）更适配你工程的一点。
- 版本 `1.1.1`，**2025-06-11 发布，之后没有新版本**（npm registry 实测）。月下载 **152,934**（全类目最高，生态最成熟）。
- 依赖为 **0 个 runtime dependency**（package.json 无 `dependencies`），打包进 exe 无问题。
- API（README 原文）：`displacementScale=70`、`blurAmount=0.0625`、`saturation=140`、`aberrationIntensity=2`、`elasticity=0.15`、`cornerRadius=999`、`overLight=false`、`mouseContainer`（让整个父容器驱动鼠标位置）、`mode: "standard" | "polar" | "prominent" | "shader"`（**`shader` 最准但作者自己标注 "not the most stable"**）。
- **README 自己的免责声明（原文）**：
  > ⚠️ NOTE: Safari and Firefox only partially support the effect (displacement will not be visible)
- 浏览器支持（README 原文）：Safari / Firefox 只有 frost + 高光，**位移不生效**——也就是说这两个浏览器上你会得到一个"普通毛玻璃"，不是坏掉，但也不是液态玻璃。
- 风险点：它是"组件式封装"，把位移强度、圆角、padding 都收进 props；嵌进你现有的 Radix + shadcn 结构时，**它包裹的是 children，不改变你卡片的 hover/点击语义**，但 `overflow`、`backdrop-filter` 的 backdrop root 规则容易和你的 `sticky` 顶部栏互相干扰（见 §6）。

---

## 3. 其他开源实现（按技术路线分组）

### 3.1 SVG 位移（真折射）路线

**samasante/liquid-glass**（`@samasante/liquid-glass`）

- URL: https://github.com/samasante/liquid-glass ／ 文档 https://glass.samasante.com
- Star **539**；MIT；npm 0.1.1，2026-06-23 发布；月下载 20,741；**0 runtime dependencies**，peer 仅 react/react-dom。
- 技术路线与上面两个都不同（README 原文核实）：**不用 `backdrop-filter`，而是在被包裹元素自身用 `filter: url()`**，配合 SDF（有符号距离场）光栅化的位移贴图 + 3 遍 RGB 分离做色散。
- 它的核心卖点是"跨引擎"：**Chrome/Safari/Firefox 都能看到折射**，因为 `filter: url()`（作用在自己内容上）在 Gecko/WebKit 是支持的，而 `backdrop-filter: url()`（作用在背后内容上）只有 Chromium 支持。
- 作者自己列的限制（BROWSERS.md 原文）：
  - **"Very wide panels (a dock-style bar) shouldn't use a single stretched displacement lens, because it blooms an oval."** → 宽条（顶部栏那种）会变成椭圆鼓包，作者建议这类一律**只用 frost（磨砂），把透镜留给"内容尺寸"的元素**。
  - **"SVG filters are GPU-bound. Very large lenses or many simultaneous instances can cost frames; keep lenses content-sized and prefer one or a few."** → 直接印证"长列表别用"。
  - Safari 上因为 WebKit 有 source-graphic 尺寸上限，强制 1× 渲染，且做了 4 处 WebKit 专用 hack（禁超采样、位移贴图仅在形状变化时重建、每次更新 bump filter id 规避 WebKit 的 id 缓存、specular 从原始贴图采样）。
- 风险：项目极新（0.1.x），单作者，文档里对 Safari 的修复非常"手工艺"，长期维护不确定。

**SquareMediaGroup/glassfx**（`glassfx`）

- URL: https://github.com/SquareMediaGroup/glassfx ／ Star **0**；MIT；0.3.0，2026-06-14；月下载 **51**。
- 纯 CSS + ~1KB JS，`backdrop-filter: url()` + `feDisplacementMap`，附带 `Glass` / `GlassFilter` 的 React 导出。
- README 原文明确：**"Refraction (`backdrop-filter: url()`) is currently Chromium-only"**，Safari/Firefox 自动降级为 depth + frost；<768px 直接关掉折射；**已内建 `prefers-reduced-motion` 与 `prefers-reduced-transparency` 支持**，"glass-strong" 预设明确标注是给 **headers/toolbars** 用的、且带 `glass-legible-text`（给浅色玻璃上的文字加极淡 text-shadow 保可读性）。
- 评价：**设计思路最贴近你的场景**（toolbar 用 strong、弹层用 opaque、文本可读性单独 class、无障碍媒体查询内建），但 star 和下载量近乎为零，等于把维护风险全部自己承担（代码量很小，可以 vendor 进仓库自行维护）。

**react-glass-ui**（`react-glass-ui`）

- URL: https://github.com/YashNK/react-glass-ui ／ Star **7**；MIT；1.2.2，2025-11-16；月下载未核实。
- 提供 `GlassCard` / `GlassButton` / `GlassInput`，props 有 `distortion`（0-100）、`chromaticAberration`、`blur`、`saturation`、`brightness`。
- README 原文：**"offers limited support across all modern browsers, but is optimized for Chrome for the best visual quality and performance."**
- 评价：**组件形态最像你要的东西**（尤其是 `GlassInput` 对搜索框），但 star 太少、单作者、明确偏 Chromium。

**einui/einui**（shadcn registry 形态）

- URL: https://github.com/einui/einui ／ 预览 https://ui.eindev.ir ／ Star **143**
- 许可证：仓库 **LICENCE 文件是 MIT**（已读原文）；README badge 写的是 ISC —— 以 LICENSE 文件为准，但**这个不一致本身就值得警惕**。
- 技术定位：**不是折射方案**，而是一套 shadcn registry 格式的"液态玻璃风格组件"，构建在 **Radix UI + Tailwind v4 + React 19** 上，用 `shadcn` CLI 拉进项目。
- 对你的价值：**风格/设计语言参考（配色、透镜高光、边框高亮、层次阴影的写法）比它的代码更有用**。直接使用有两个不兼容点：Tailwind v4（你是 3.4）和 React 19（你是 18）。
- 同类：`aryankholqi/liquid-glass-cli`（npm `liquid-glass-cli` 1.2.0，MIT，**Star 仅 2**，走 "shadcn 风格把代码 copy 进项目、不作为依赖" 的路子）。

### 3.2 WebGL / WebGPU 路线

**naughtyduk/liquidGL**（npm `liquid-gl`）

- URL: https://github.com/naughtyduk/liquidGL ／ demo https://liquidgl.naughtyduk.com ／ npm `liquid-gl`
- Star **868**（GitHub API 实测）；**许可证：仓库未标注 SPDX**（shields 返回 "not specified"），但 npm `liquid-gl` 包声明 `"license": "MIT"` —— **两处不一致，商用前需自行确认**。
- 版本 **2.1.1**（README 顶部版本号）；月下载 **12,564**。
- 技术路线：**WebGL shader + 全页 DOM 快照**。"turns any fixed or sticky-positioned element into a perfectly refracted, glossy glass pane"。
- 已核实的、对你很关键的限制（全部 README 原文）：
  - **快照开销**：自研光栅器 median **55.5ms**、min 54.1 / max 57.5、**worst single stall 37.8ms**（Chrome 150，`resolution: 2`，2880×10036 输出）；对比 html2canvas median 86.3ms。→ **一次快照 ≈ 3~4 帧**。
  - **CORS**："any **image** content inside the `target` element must have permissive `Access-Control-Allow-Origin` headers set to prevent CORS issues." → 你的结果卡片全是外站缩略图（B 站/小红书等），走 canvas 快照时是实打实的坑（除非缩略图由本地后端反代/本地缓存输出）。
  - **超长文档**："Extremely long documents can exceed GPU texture limits, causing memory or performance issues. Consider segmenting very long pages or reducing the `resolution` parameter." → 你几十上百条卡片的列表正属于此类。
  - Safari 不稳："Safari can be unstable when the liquid element(s) are more than 50% of the viewport width or height."
  - 忽略 `position: fixed` 元素；多实例**必须共享同一 z-index**；`shadow`/`tilt`/`specular` 在实例多时要慎用。
  - 官方 FAQ 声称"shared canvas，测到 30 个元素没问题"——但那是营销页上的短页面，**不等于长列表滚动**。
- 评价：**和你的需求方向相反**。它是给"营销落地页上的一个 hero 玻璃面板"设计的，不是给"数据密集型长列表工具"设计的。

**AndrewPrifer/liquid-dom**（`@liquid-dom/*`）

- URL: https://github.com/AndrewPrifer/liquid-dom ／ Star **2.5k**（shields 实测，GitHub API 2498，created 2026-04-18）
- 许可证：**MIT**（shields/API），npm 包元数据里 license 字段为空。
- monorepo：`@liquid-dom/core`（WebGPU 渲染器）、`@liquid-dom/react`（**React 19** 绑定）、`@liquid-dom/three`、`@liquid-dom/r3f`、`@liquid-dom/layout`。
- **致命限制（README 原文）**：
  > The liquid-glass renderer **requires WebGPU**. DOM-backed `Html` content also requires the experimental **HTML-in-Canvas API**, which is currently available **only behind Chrome's Canvas Draw Element flag: `chrome://flags/#canvas-draw-element`**.
- 评价：**对你不适用**。要求用户去开 Chrome flag 的东西不能进 exe 分发。star 多说明方向热，不代表可用。

**iyinchao/liquid-glass-studio**（`@labs/liquid-glass`）

- URL: https://github.com/iyinchao/liquid-glass-studio ／ Star **688**；**MIT**；"powered by WebGL2 & WebGPU"；npm `@labs/liquid-glass` 1.0.1（2026-06-06）。**未实测**，仅登记为候选。

**ybouane/liquidglass**（`@ybouane/liquidglass`）

- URL: https://github.com/ybouane/liquidglass ／ Star **476**；许可证 GitHub 显示 "not specified"；npm 1.0.3（2026-04-10）声明 MIT。
- 定位："Apply realistic glass refraction, blur, chromatic aberration and lighting effects to any HTML element **using WebGL shaders**"；README 与 API 未逐一核实。

**dashersw/liquid-glass-js**（npm `liquid-glass-js`）

- URL: https://github.com/dashersw/liquid-glass-js ／ Star **983**；**MIT**（shields 实测）；npm `liquid-glass-js` 0.1.0（2026-06-10）。
- 注意：npm 上 `liquid-glass-js` 的 repository 字段指向 `github.com/eamonliu/liquid-glass-js`，**与同名高 star 仓库不是同一个**——npm 包名与仓库的对应关系存疑，使用前需核对。**技术路线未核实。**

### 3.3 纯 CSS / SVG 滤镜 Demo（可抄代码，不建议当依赖）

| 仓库 | Star | 许可证 | 路线 | 评价 |
| --- | --- | --- | --- | --- |
| [archisvaze/liquid-glass](https://github.com/archisvaze/liquid-glass) | 768 | 仓库未标注 | 双引擎：SVG `feDisplacementMap`+`backdrop-filter`（**Chrome/Mac only**）／Three.js 全屏 shader（全浏览器） | README 自带完整浏览器支持矩阵，两个引擎的差异写得最清楚；**是 Demo 不是库**，可抄 IOR/bezel/厚度参数化思路 |
| [lucasromerodb/liquid-glass-effect-macos](https://github.com/lucasromerodb/liquid-glass-effect-macos) | 825 | 仓库未标注 | 纯 CSS + SVG 滤镜（按钮尺度） | 极小 demo，适合看"按钮级"玻璃长什么样 |
| [childrentime/liquid-glass](https://github.com/childrentime/liquid-glass) | 16 | 未标注 | TS，附中文说明 `LIQUID_GLASS_EFFECT_EN.md` | 中文资料，可读 |
| [sohumsuthar/liquid-glass](https://github.com/sohumsuthar/liquid-glass) | 1 | 未标注 | SVG 滤镜 | **唯一价值：指出 `colorInterpolationFilters="sRGB"` 是必须的**——linearRGB 下 128 中性值会漂移，整个背景位移 |
| [shuding/svg-shaders](https://github.com/shuding/svg-shaders) | 190 | **MIT** | "Composable SVG Shaders" | shuding 那套的通用化底座，如果你想自己写位移贴图，从这里起步 |

另外两个**与 Web 无关、仅供确认"官方观感"**：`Kyant0/AndroidLiquidGlass`（3.8k，Apache-2.0，Compose Multiplatform）、`callstack/liquid-glass`（1.7k，MIT，React Native —— 不是 Web React，**别被名字骗了**）。

---

## 4. 纯 CSS 能到什么程度？和真折射差在哪

### 能做到（全部可用，且你的工程已有基础）

```css
/* 你现在的 .glass-panel 已经是这一档，再补 3 条就基本到顶 */
.glass-tier0 {
  background: rgb(var(--glass-bg));                       /* 半透明着色 ← 已有 */
  backdrop-filter: blur(14px) saturate(140%) brightness(1.05);  /* ← 可加 saturate/brightness */
  -webkit-backdrop-filter: blur(14px) saturate(140%) brightness(1.05);
  border: 1px solid rgb(var(--glass-border));             /* ← 已有 */
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,0.55),                 /* 顶部高光边：玻璃感 80% 来自这里 */
    inset 0 -1px 0 rgba(255,255,255,0.12),
    0 8px 26px rgba(50,105,145,0.10);                     /* 你已有 cyber-card 阴影 */
}
```

可模拟的：模糊（frost）、提饱和、提亮、着色（tint）、内高光边、外投影、圆角。`prefers-reduced-transparency`、`prefers-reduced-motion` 都可用（Chrome 119+）。

### 做不到的（这就是"真折射"的差别）

1. **边缘弯曲**：真玻璃在圆角处把背后的内容"吸"进去、边缘压缩、中心几乎不偏折。纯 CSS 的模糊是**各向同性的**，边缘和中心模糊程度一样，所以看起来像"磨砂塑料片"，不像"一块有厚度的玻璃"。
2. **色散（chromatic aberration）**：真玻璃边缘把 R/G/B 分开偏移（蓝偏得最多）。CSS 滤镜链无法做**空间可变的**通道位移——`drop-shadow` 可以给通道偏移但是全图统一方向，看起来是"重影"而不是"色散"。
3. **高光随视角/指针流动**：可以用 `radial-gradient` + CSS 变量 + `mousemove` 手搓一个跟随光斑（glassfx 就是这么干的，~1KB JS），观感能到 70%，但**不会随背后内容变化**。
4. **放大/收缩（magnify）**：纯 CSS 完全没有。这是 shuding/liquid-glass 的位移贴图最抓眼的部分。

**一句话**：纯 CSS 大约能拿到"液态玻璃观感"的 **70~80%**，差的 20~30% 全在"边缘"——而人的眼睛恰恰是被边缘骗到的。另一个反直觉的实测经验（[Liquid glass needs a ladder](https://dev.to/dimonb19a/liquid-glass-needs-a-ladder-394j) 作者的踩坑）：**透镜放在大面板上会翻车**——背景里任何高对比直线穿过透镜圆角时会"折出个拐点"，没有东西框住这个弯折，看起来像渲染 bug 而不是玻璃。他最后把透镜**收缩到"小尺寸 chrome"**（pill 导航、浮动控件、小圆），把大面板退回噪声扰动/纯模糊。

---

## 5. 浏览器兼容性（重点，且对你的部署形态有决定性影响）

### `backdrop-filter` 本体：**已经没问题了**

web-platform-dx 实测数据：

- Chrome 76 (2019-07-30)、Edge 79 (2020-01-15)、Firefox 103 (2022-07-26)、Safari 18 / iOS 18 (**2024-09-16**)
- 状态：**Baseline "Newly Available" since 2024-09-16**，预计 2027-03-16 成为 Widely Available
- 用量：Chrome 平台约 **35.6% 的页面加载**使用
- 已进入 **Interop 2025**
- 来源：https://web-platform-dx.github.io/web-features-explorer/features/backdrop-filter/ ／ https://caniuse.com/css-backdrop-filter ／ https://developer.mozilla.org/en-US/docs/Web/CSS/backdrop-filter

→ **你的 `backdrop-blur-md` 顶部栏和 `.glass-panel` 在所有现代浏览器上都安全。**

### `backdrop-filter: url(#svg-filter)`（真正的折射）：**Chromium only，且 Safari 有严重 bug**

- **Safari / WebKit：不支持。** [WebKit Bugzilla #245510](https://bugs.webkit.org/show_bug.cgi?id=245510)（2022-09-21 报告，**至今状态仍是 NEW**，P2）。2026-07-16 有人提了 PR（WebKit/WebKit#68613 / #68614），2026-09-05 的最新评论更糟：
  > On trunk, the testcase linked from this bug doesn't just render unfiltered. **It crashes the GPU process, repeatedly, for as long as the page is open.**
- **Firefox / Gecko：这是最危险的一种失败模式**。据 [Liquid glass needs a ladder](https://dev.to/dimonb19a/liquid-glass-needs-a-ladder-394j)（前端工程师实测总结）：
  > Firefox does something worse — it **parses** it as valid, then **renders nothing**, which turns your beautiful glass panel into a **fully transparent hole** with text floating over whatever's behind it.
  > **Firefox accepts the declaration as syntactically valid — so your `@supports` checks pass — and then renders nothing.**
  （注意：WebKit bug #245510 的 comment 4 里有人报告 Firefox 是**支持** `backdrop-filter: url()` 的，与上述实践总结冲突。**这种"资料互相矛盾"本身就是结论：不要依赖它，必须在目标浏览器上实测。**）
- **Chromium：可用，但有一个竞态**：如果 CSS 在 SVG 滤镜节点进入 DOM 之前就引用了它，加载瞬间会闪一下"透明"。
- 标准化状态：W3C SVG WG 正在讨论 [w3c/svgwg#1142 "Filter Effects: define interoperable backdrop displacement/refraction for 'liquid glass' UI"](https://github.com/w3c/svgwg/issues/1142) —— 说明**互操作性目前根本不存在**，这是标准层面的空白。

→ **绝对不要写裸的 `backdrop-filter: url(...)`。** 要用的话必须：把规则挂在属性选择器上（如 `html[data-liquid-glass]`），由运行时确认"滤镜节点已在 DOM"且"引擎支持"后才设置这个属性；否则静默留在第 0 层。

### `filter: url()`（作用在自己内容上，samasante 路线）：**Gecko/WebKit/Blink 都支持**

这是唯一能跨引擎拿到"位移"的路径。samasante 的 BROWSERS.md 声称三个引擎的 displacement / chromatic aberration / specular 全部 ✅，并说用 Playwright 对着 Chromium 和 WebKit 验证过（**注意：它没有说对 Gecko 做过自动化验证**，只写了"Works via `filter: url()`"）。这条路线代价是：**只能折射"你包裹的那份内容"，不能折射"面板背后的实时页面"**——而后者才是"玻璃盖在内容上"的观感。

### `prefers-reduced-transparency`：**Chromium only**

web-platform-dx 实测：Chrome/Edge 119 (2023-10) 支持；**Firefox 不支持**（bug 1822176）；**Safari 不支持**，且立场是 privacy 顾虑（WebKit standards-positions #145，bug 175497）。

→ 想做无障碍降级，**`prefers-reduced-transparency` 只能覆盖一部分用户**，必须同时提供一个**应用内开关**（你自己的 theme store 已有基础，`webui/src/store/themeStore.ts`）。

---

## 6. 性能坑（针对"长列表 + 逐卡片滤镜"）

### 逐卡片用 `backdrop-filter`

- `backdrop-filter` 会强制浏览器为**每个**应用它的元素做一次"读取背后像素 → 过滤 → 重新合成"。N 个卡片 = N 次 backdrop 采样。
- **backdrop root 规则会咬人**（MDN 原文）：`filter` / `opacity<1` / `mask` / `clip-path` / `backdrop-filter` / `mix-blend-mode` / 相应 `will-change` 的元素都会成为**新的 backdrop root**，其**子元素看不到该祖先之上的内容**。→ 你在卡片上再加一层面板，会意外让"玻璃失去背景"或者让副作用只作用在局部。
- 有真实用户案例：Mozilla 支持论坛 "[Severe scroll jank with sticky header + backdrop-filter + lazy images](https://support.mozilla.org/questions/1531518)" —— **sticky header + backdrop-filter + 懒加载图片**正是你的组合（粘性顶栏 + 结果列表缩略图懒加载）。
- 社区普遍实践（见 [eslint-custom-rules 的 no-compositing-layer-props 规则说明](https://github.com/BluMintInc/eslint-custom-rules/blob/main/docs/rules/no-compositing-layer-props.md)）：**不要滥用会强制 GPU 合成层的属性**（`transform` / `filter` / `will-change`），每层都吃 GPU 显存。

### 逐卡片用 SVG 位移滤镜（`feDisplacementMap`）

更糟，理由有三：

1. **位移贴图必须逐元素生成/匹配形状**。半径、尺寸一变就要重建贴图。samasante 为此专门做了"仅在**形状**变化时重建贴图，移动时不重建"的优化——反过来说，**列表里每个卡片形状不同 = 每个都要一份贴图**。
2. **滤镜是按尺寸付钱的**。samasante 的 BROWSERS.md 原文：**"SVG filters are GPU-bound. Very large lenses or many simultaneous instances can cost frames; keep lenses content-sized and prefer one or a few."**
3. **Chromium 每次滤镜引用变更都可能触发重新光栅化**；配合滚动时的持续重绘，会被反复触发。

### WebGL 快照路线（liquidGL 这类）

- 一次全页快照 **median 55.5ms**（liquidGL 自测数据，已引于 §3.2）≈ 丢 3~4 帧。
- 超长文档会**超出 GPU 纹理上限**（官方警告原文）。
- 卡片里的外站图片触发 **CORS/canvas 污染**（官方警告原文）。

### 已知优化建议（可直接落地的清单）

1. **只在悬浮/少量元素上用**：透镜限 1~2 个实例，绝不上列表。这是 samasante、liquidGL、dev.to 三处独立来源的一致结论。
2. **避免在 `filter` 里嵌 `backdrop`，也避免 `backdrop-filter` 里塞 `url()`**（Firefox 变空洞 + Safari 崩 GPU 进程 + 上述 backdrop root 叠加问题）。
3. **`will-change` 用到"即将变化"为止，用完即撤**，不要长期挂着。你的 `index.css:409` 已有 `.will-change-transform`，注意别把它和滤镜叠在同一元素上。
4. **保持模糊半径跨降级层级恒定**（[ladder 一文的核心经验](https://dev.to/dimonb19a/liquid-glass-needs-a-ladder-394j)）：如果第 0 层 `blur(14px)`、第 2 层 `blur(4px)`，升级瞬间页面会"突然变薄"，观感像 bug。**只换位移，不换模糊。**
5. **把透镜限制在"小尺寸 chrome"**：pill 按钮、图标按钮、搜索框右侧的小按钮、下拉箭头。大面板（顶部栏整条、统计面板）**只用 frost**——samasante 明确说宽条会"blooms an oval"，dev.to 作者说大面板上透镜"看起来像渲染 bug"。
6. **静态化**：如果只是要"看起来像玻璃"，用**预烘焙的静态 SVG/PNG 高光层**（不随背景变化），成本几乎为零，视觉收益却拿走了大部分。
7. **列表项**：`content-visibility: auto` / 虚拟滚动（你已有几十上百条）+ 纯色卡片，比任何滤镜都划算。

---

## 7. 可访问性 / 可读性风险

- **文字对比度是最大的敌人**。半透明玻璃后面的内容是**动态变化**的：卡片后面可能是深色缩略图，滚动时同一行文字的背景会从浅变深，**静态的 WCAG 对比度检查会通过，实际运行时会失败**。玻璃面板的 tint 必须足够不透明（你的 `--glass-bg` 浅色 **85%**、暗色 **72%** 已经相当保守，这是对的；暗色 72% 在三平台图标混排时仍有风险）。
- **位移会让文字"变形"**：如果透镜作用在文字上（shuding/Vaso 路线的位移图层会覆盖到 children），文字在小位移下会发虚、在边缘处会扭曲。**必须保证"文字在最上层、不参与位移"**——rdev/samasante 都是这个约定（"children render crisp" / "children are the crisp layer on top"）。
- **`prefers-reduced-transparency` 覆盖不全**（Chrome/Edge only，Firefox/Safari 不支持）→ **必须给应用内开关**（你的 `themeStore` 可直接扩展成 `glass: 'full' | 'reduced' | 'off'`）。
- **`prefers-reduced-motion`**：鼠标跟随的 elasticity/tilt 属于动效，必须在这个媒体查询下关掉（glassfx 已内建，自己写要注意）。
- **焦点可见性**：`backdrop-filter` 元素常被误用为按钮容器，导致 `:focus-visible` 的 ring 被 `overflow: hidden` 裁掉。你的 `ResultTools.tsx:118`、`SearchBar` 都依赖 `focus-visible:ring-2`，加玻璃层时要检查 ring 没被裁。
- **`prefers-contrast` / 高对比模式**：Windows 上用户开"高对比度"时，所有半透明都会退化成纯色。别把**唯一的**状态指示（如平台状态的绿点）放在玻璃层的高光里。

---

## 8. 结论：用在哪些局部、避免哪些地方

### ✅ 适合（按推荐度排序）

| 位置 | 建议档位 | 理由 |
| --- | --- | --- |
| **顶部栏（`Header.tsx:246`）** | **第 0 层（frost）+ 细高光边**，**不要透镜** | 已经是 `sticky + backdrop-blur-md`，是玻璃效果的最佳载体：面积固定、只有 1 个、文字在自身层不受影响。samasante 明确警告宽条透镜会"blooms an oval"。加 `inset 0 1px 0 rgba(255,255,255,.55)` 高光边 + `saturate(140%)` 就能明显"更像玻璃"。 |
| **底部作者栏 / 浮动状态条（`AuthorFooter.tsx`）** | 第 0 层 | 同上，固定位置、单个。 |
| **搜索框外框（`SearchBar.tsx:154` 容器）** | 第 0 层（frost + tint），**透镜只给右侧的小按钮/图标** | 搜索框是主要输入元素，用户的注意力全在里面的文字上；模糊可以，位移不行。`SearchBar.tsx:194` 那个 `h-[56px] rounded-[15px] bg-brand` 的搜索按钮是**透镜的最佳候选**：小、圆角、pill 形、非文字承载。 |
| **弹层 / 下拉（`SearchPopover.tsx:55`、`ResultTools.tsx:97`、`SearchPage.tsx:321`）** | 第 0 层**偏不透明**（`glass-strong` / `glass-opaque` 那种） | 弹层悬浮在"内容 + 滚动"之上，是透镜观感最好的位置，但**可读性优先**：glassfx 专门有 `glass-opaque` class 就是给 "dropdowns/popovers over busy content"。你可以给弹层**边缘**做透镜、面板做不透明。 |
| **小尺寸 chrome：图标按钮、pill 徽标、`ThemeToggle` / `LanguageSwitch`（`layout/`）** | **第 2 层透镜的唯一天然场** | 小、圆角、非文字承载、数量可控（≤5）。这正是 dev.to 作者说的 "small chrome" 与 samasante 说的 "content-sized elements"。 |
| **空状态 / 欢迎插画（`SearchPage.tsx` 空态区域）** | 第 2 层透镜 | 屏幕上没有别的玻璃、不滚动、没有性能压力，是"炫技"最安全的地方。 |

### ❌ 应当避免

| 位置 | 原因 |
| --- | --- |
| **结果卡片（`ResultCard.tsx`，`grid-cols-[104px_minmax(0,1fr)]`，几十~上百个）** | **性能红线**。每卡片一个 backdrop 采样或 SVG 位移贴图，滚动时逐帧重算；卡片里还有外站缩略图（liquidGL 路线会 CORS 污染 canvas）。另外 `hover:-translate-y-0.5 transition-all` 已经会产生合成层，再叠滤镜是双倍代价。 |
| **平台状态卡片（`PlatformStatus.tsx`）** | 里面是**文字密集 + 状态色圆点**（登录态/限流/失败）。玻璃会让"绿点/黄字"的对比度随背后内容漂移，而这恰恰是你最需要用户一眼看清的信息。**保持不透明。** |
| **筛选/统计面板（`ResultTabs.tsx:137/160/191`、`SearchStatistics.tsx:36`）** | 同上：`text-[10.5px]` 级别的小字号 + 边框分隔线，玻璃会吃掉细节；且它们就在长列表上方，滚动时反复重绘。 |
| **整页背景 / body** | 无意义地让所有内容都变成 backdrop root，副作用大收益小。 |
| **错误/警告提示（`SearchPage.tsx:202-236` 的 warn/danger 框）** | 语义色 + 玻璃 = 对比度不可控。**警告必须最高对比度。** |
| **任何"宽条"上的透镜**（顶部栏整条、底部栏整条、统计面板整条） | samasante BROWSERS.md 原文：宽面板用单个拉伸透镜会 "blooms an oval"。 |

---

## 9. 低风险试点最小方案（建议直接照做）

**目标：不引入任何新依赖、不改动现有组件结构、随时可回退。**

### 阶段 0（今天，~20 行 CSS，零风险）

只改 `webui/src/index.css` 的 `.glass-panel` 两个类，把"毛玻璃"提升到"第 0 层玻璃"：

```css
.glass-panel {
  background: rgb(var(--glass-bg));
  backdrop-filter: blur(14px) saturate(145%) brightness(1.06);
  -webkit-backdrop-filter: blur(14px) saturate(145%) brightness(1.06);
  border: 1px solid rgb(var(--glass-border));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.5),     /* 顶部高光 */
    inset 0 -1px 0 rgba(255, 255, 255, 0.10),
    0 8px 26px rgba(50, 105, 145, 0.10);
}
/* 暗色主题下高光要弱一些，否则发灰 */
.dark .glass-panel { box-shadow: inset 0 1px 0 rgba(255,255,255,0.10), inset 0 -1px 0 rgba(0,0,0,0.25), 0 8px 26px rgba(0,0,0,0.35); }
```

并把 `Header.tsx:246` 的 `bg-cyber-bg-primary/85 backdrop-blur-md` 换成 `glass-panel`（或保留类名、只加高光边）。
**验收**：浅色/暗色两主题下顶栏文字对比度不变（用 DevTools 取色或 axe 抽查），滚动长列表时 DevTools Performance 面板无掉帧。

### 阶段 1（可选，仅一个元素，~40 行）

在**搜索按钮**（`SearchBar.tsx:194`）上加"透镜"。**不要引入 rdev/liquid-glass-react**——它虽然成熟（6.1k star、MIT、React >=18 兼容），但它是个封装组件，会接管你按钮的 DOM 结构和样式。更稳的做法是**手写一个最小透镜**，参考 shuding 的 `liquid-glass.js`（MIT，1.2k star，可整段抄）+ `shuding/svg-shaders`（MIT）：

1. 一个 `<svg width="0" height="0">` 挂在 App 根部，内含 `<filter id="lg-<uid>"><feImage id="lg-map"/><feDisplacementMap in="SourceGraphic" in2="lg-map" xChannelSelector="R" yChannelSelector="G"/></filter>`。
2. `filter` 必须带 `filterUnits="userSpaceOnUse"` 和 **`colorInterpolationFilters="sRGB"`**（后者是踩坑点，见 §3.3 sohumsuthar）。
3. 用 canvas 2D 画一张 圆角矩形 SDF 位移贴图（贴图尺寸 = 按钮尺寸，不是全屏），`toDataURL()` 赋给 `feImage`。
4. 只在小按钮上应用 `filter: url(#lg-uid)`；**children 文字放在 filter 之外的层**，保持清晰。
5. **gate（必须做）**：
   ```
   仅当 (a) 运行时探测到 Chromium 内核
        (b) SVG filter 节点已 mounted 并可见
        (c) 用户开关 = on
        (d) !prefers-reduced-motion
        (e) 精确指针（非触屏）
   时才在 <html> 上设置 data-liquid-glass 属性；
   CSS 规则写成 html[data-liquid-glass] .lg-lens { filter: url(#lg-uid); }
   ```
   —— 这样 Firefox/Safari/任何异常都自动退回阶段 0 的纯模糊，**不会出现"透明空洞"**。
6. 加**应用内开关**：扩展 `webui/src/store/themeStore.ts`，加 `glass: 'full' | 'reduced' | 'off'`，默认 `reduced`，把 `prefers-reduced-transparency`（Chrome/Edge 119+ 可用）作为**额外**的默认覆盖。

### 明确不要做的事

- ❌ 不要给 `ResultCard` 加任何滤镜（哪怕是 `backdrop-filter`）。这是最容易"看起来很美、用起来卡死"的地方。
- ❌ 不要用 `liquidGL` / `liquid-dom`（前者快照 55ms + CORS + 超长文档纹理上限；后者要 Chrome flag）。
- ❌ 不要把 `backdrop-filter: url(...)` 写进裸 CSS（Firefox 空洞 / Safari 崩 GPU 进程 / Chromium 加载竞态）。
- ❌ 不要为了这个效果升级到 React 19 或 Tailwind 4（einui 就是 v4 + React 19，不值得为了皮折腾基座）。
- ❌ 不要用 CDN 引入任何东西（你是离线 exe）。上述所有候选的 npm 包都是 0 runtime dependency 或纯 CSS/图片，**必须走 npm + Vite 打包**。

---

## 10. 一页速查表

| 方案 | URL | Star | 许可证 | 技术路线 | React 集成 | 性能风险 | 可访问性风险 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| shuding/liquid-glass | [repo](https://github.com/shuding/liquid-glass) | 1.2k | MIT | SVG `feImage`+`feDisplacementMap`+`backdrop-filter:url()` | **大**（console 贴片，无 npm） | 高 | 中高（可作位移层覆盖文字） |
| huozhi/vaso | [repo](https://github.com/huozhi/vaso) | 345 | README 称 MIT，仓库未标 | shuding 的 React 版（位移图层） | 小 | 中高 | 中 |
| rdev/liquid-glass-react | [repo](https://github.com/rdev/liquid-glass-react) | 6.1k | MIT | SVG 位移 + `backdrop-filter` | **小**（peer react>=18 ✅） | 中高 | 中（children 清晰） |
| samasante/liquid-glass | [repo](https://github.com/samasante/liquid-glass) | 539 | MIT | `filter:url()` 作用于自身 + SDF + RGB 色散（**跨引擎**） | 小（headless，0 依赖） | 中 | 中 |
| naughtyduk/liquidGL | [repo](https://github.com/naughtyduk/liquidGL) | 868 | 仓库未标 / npm 声明 MIT | WebGL + 全页 DOM 快照 | 中（命令式 `liquidGL({target})`） | **高**（快照 55ms / CORS / 纹理上限） | 中 |
| AndrewPrifer/liquid-dom | [repo](https://github.com/AndrewPrifer/liquid-dom) | 2.5k | MIT | WebGPU + HTML-in-Canvas | 大（React 19） | 中 | 低 |
| SquareMediaGroup/glassfx | [repo](https://github.com/SquareMediaGroup/glassfx) | 0 | MIT | CSS + `backdrop-filter:url()` → Chromium only | 小（有 React 导出） | 中 | **低**（内建 reduced-motion / reduced-transparency / legible-text） |
| react-glass-ui | [repo](https://github.com/YashNK/react-glass-ui) | 7 | MIT | SVG 滤镜组件（GlassCard/Button/Input） | 小 | 中 | 中 |
| einui/einui | [repo](https://github.com/einui/einui) | 143 | LICENSE 文件 MIT（badge 写 ISC，不一致） | shadcn registry，**非折射**，Radix+TW4+React19 | 中（版本不兼容） | 低 | 低 |
| archisvaze/liquid-glass | [repo](https://github.com/archisvaze/liquid-glass) | 768 | 未标注 | SVG 位移 ／ Three.js 双引擎 **Demo** | —（抄代码） | 中 | — |
| lucasromerodb/…-macos | [repo](https://github.com/lucasromerodb/liquid-glass-effect-macos) | 825 | 未标注 | 纯 CSS + SVG 滤镜 **Demo** | —（抄代码） | 低 | — |
| dashersw/liquid-glass-js | [repo](https://github.com/dashersw/liquid-glass-js) | 983 | MIT | **未核实**（npm 包与仓库对应关系存疑） | 未核实 | 未核实 | 未核实 |
| ybouane/liquidglass | [repo](https://github.com/ybouane/liquidglass) | 476 | 仓库未标 / npm 声明 MIT | WebGL shader | 未核实 | 未核实 | 未核实 |
| iyinchao/liquid-glass-studio | [repo](https://github.com/iyinchao/liquid-glass-studio) | 688 | MIT | WebGL2 + WebGPU | 未核实 | 未核实 | 未核实 |
| guillaume-flambard/liquid-ui | [repo](https://github.com/guillaume-flambard/liquid-ui) | 2 | MIT | — | — | — | **仓库已 archived，勿用** |

**标注说明**：Star 数来自 GitHub API（2026-09 实测）或 shields.io，两者一致时写单值；许可证凡写"仓库未标注"的，均为 shields.io 返回 `not specified`，与 npm 包声明不一致的已单独说明。凡标"未核实"的项目**没有**逐个读源码/README，**不要**据此选型。

---

## 参考链接

- [MDN `backdrop-filter`](https://developer.mozilla.org/en-US/docs/Web/CSS/backdrop-filter)（含 backdrop root 规则原文）
- [web-platform-dx: backdrop-filter 兼容性](https://web-platform-dx.github.io/web-features-explorer/features/backdrop-filter/) ／ [caniuse](https://caniuse.com/css-backdrop-filter)
- [web-platform-dx: prefers-reduced-transparency](https://web-platform-dx.github.io/web-features-explorer/features/prefers-reduced-transparency/)
- [WebKit Bugzilla #245510](https://bugs.webkit.org/show_bug.cgi?id=245510)（Safari `backdrop-filter: url()` 不支持 + GPU 进程崩溃）
- [w3c/svgwg#1142](https://github.com/w3c/svgwg/issues/1142)（标准层面尚未定义可互操作的 backdrop 位移）
- [Liquid glass needs a ladder](https://dev.to/dimonb19a/liquid-glass-needs-a-ladder-394j)（四层降级阶梯 + Firefox "解析但不渲染"陷阱 + 大面板翻车经验）
- [Mozilla 支持论坛：sticky header + backdrop-filter 滚动卡顿](https://support.mozilla.org/questions/1531518)
- [eslint 规则说明：避免强制 GPU 合成层](https://github.com/BluMintInc/eslint-custom-rules/blob/main/docs/rules/no-compositing-layer-props.md)
