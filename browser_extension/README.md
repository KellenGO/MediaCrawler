# MediaCrawler 会话同步助手（Chrome / Edge MV3 扩展）

把"当前浏览器已登录的平台会话"安全同步到本地 MediaCrawler 聚合搜索网站
（仅 `http://127.0.0.1:8080`），供后台无头搜索复用登录态。

## 安装（加载已解压扩展）

1. 打开 `chrome://extensions`（Edge 为 `edge://extensions`）；
2. 打开右上角 **开发者模式**；
3. 点击 **加载已解压的扩展程序**；
4. 选择本目录 `browser_extension/`；
5. 刷新本地网站的"账号设置"页面。

## 使用流程

1. 在当前浏览器（Chrome 或 Edge）登录平台官方网站（小红书 / 抖音 / B站 / 知乎）；
2. 打开本地网站 `http://127.0.0.1:8080` → 账号设置；
3. 点击对应平台的 **同步当前浏览器登录状态**；
4. 扩展读取该平台 Cookie 并直接发送到本地后端；
5. 后端导入独立后台 profile 并验证；验证成功后搜索即可使用该登录态（无头，不弹窗）。

## 安全设计

- **权限最小化**：仅 `cookies`、`storage`，host 权限仅限四个平台官方域名
  和本机 `127.0.0.1:8080` / `localhost:8080`；没有 `<all_urls>`。
- **content script 只注入本地网站**：仅匹配 `http://127.0.0.1:8080/*` 和
  `http://localhost:8080/*`。
- **Cookie 不经网页 JavaScript**：扩展直接用 `chrome.cookies` 读取，service
  worker 直接 `fetch` 到本地后端；网页最多只能收到
  `success / platform / verified / safe_error_code / safe_message`。
- **一次性票据**：网站先向后端申请 sync-ticket（128bit、60 秒、一次性），
  页面通过 `window.postMessage` 只传递 `ticket / platform / request_id`；
  后端校验票据后才接受 Cookie。
- **不留存**：Cookie 不写入 `chrome.storage`，不 `console.log`，只把同步
  结果元数据（时间/是否成功）存入 `chrome.storage.local` 供 popup 展示。
- **不读取**：不读取浏览历史、书签或其他网站的 Cookie。

## 文件

| 文件 | 作用 |
|------|------|
| `manifest.json` | MV3 清单（最小权限） |
| `service_worker.js` | 读 Cookie → 映射为 Playwright 格式 → POST 本地 API |
| `content_script.js` | 本地网站页面的桥接（只转发 ticket/platform/request_id） |
| `popup.html` / `popup.js` | 扩展图标弹窗（连接状态 + 平台同步状态） |

## 注意

- 后端未启动时同步会失败并提示"无法连接本地服务"，请先启动
  `python -m api.main`（监听 127.0.0.1:8080）。
- 扩展版本与网站约定的协议不匹配时，网页会提示"扩展版本不兼容"，
  请在 `chrome://extensions` 点击"重新加载"。
