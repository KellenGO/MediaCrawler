# 登录与账号（浏览器扩展 / 内置扫码 / profile）

## 一句话

应用不保存账号密码，而是把使用者的登录态放进本机 `browser_data/<平台>_user_data_dir` 持久化 profile，
之后无头搜索复用。**应用内置扫码登录是主入口**，无需安装扩展；浏览器扩展同步已有登录状态是可选加速方式。

## 代码入口

| 职责 | 位置 |
|---|---|
| 浏览器扩展（MV3） | `browser_extension/`：`service_worker.js`（读 cookie → POST 后端）、`content_script.js`、`sync_protocol.js`（wire 契约，纯函数）、`popup.*` |
| 后端账号服务（一次性票据、域名白名单、Chrome→Playwright 映射、导入 profile、验证、删除） | `api/services/accounts.py` |
| 账号 / 登录 HTTP 路由（前缀 `/api/search`） | `api/routers/search.py`：`POST /login`、`GET /login/{job_id}`、`GET /accounts`、`POST /accounts/sync-ticket`、`POST /accounts/{platform}/sync`、`POST /accounts/{platform}/verify`、`DELETE /accounts/{platform}/session` |
| 扫码登录实现（可见窗口 + 二维码） | `aggregate_search/worker.py` 的 `_run_login`（约 808 行） |
| 浏览器选择（自定义 > Chrome > Edge > 内置 Chromium） | `tools/browser_launcher.py`（`resolve_playwright_browser`） |
| profile 与登录态配置 | `config/base_config.py`：`USER_DATA_DIR`、`SAVE_LOGIN_STATE` |
| 前端账号页 | `webui/src/components/accounts/AccountsPage.tsx`、`useAccounts.ts`、`useAutoAccountSync.ts` |
| 扫码任务状态和跨页面搜索避让 | `webui/src/lib/scanLogin.ts`、`webui/src/App.tsx` |
| 前端扩展通信与批量同步 | `webui/src/lib/extensionSync.ts`、`accountBulkSync.ts`、`accountGate.ts` |

profile 目录：`browser_data/{xhs,dy,bili,zhihu}_user_data_dir`。

## 关键决定

- **扩展只是 cookie 搬运工**：从使用者日常浏览器读出 cookie，POST 给后端，
  后端导入应用自己的 profile（它不搜索、不抓取、不常驻）。
- 扩展走**一次性同步票据**（128bit、60s、单次），后端只接受 `chrome-extension://` 来源。
- **扫码登录写入的 profile 就是搜索读取的那一个**，登录后 `_verify_login_success` 会真验证一次。
- 验证必须在浏览器会话关闭之前完成；此前会话关闭后验证导致“扫码成功但报失败”。已有登录时可直接验证成功，不必再扫一次。
- 可见浏览器自身展示二维码，不另弹系统图片查看器；无头模式仍保留图片二维码。
- 重启不信任磁盘上的旧验证结论。没有扩展时，自动复核本机已有登录状态；与扩展自动同步共用冷却，避免重复操作，全部成功时不打扰。
- 切去搜索页仍保留登录轮询，任务结束后再释放搜索等待；不能因离开账号页就假定登录结束。整页刷新后仍由后端互斥兜底。
- 账号卡片只展示登录确认状态和对应操作，不再显示「可尝试搜索／暂时无法搜索」徽章。诊断是上次搜索与内部状态推导，不是实时检测；旧搜索失败不能覆盖新登录结论。保留在折叠区的记录明确标注为历史信息。
- 为什么不能「应用直接读浏览器 cookie」：**Chrome 127+ 的 App-Bound Encryption**
  让外部程序即使拿到 cookie 数据库也解不开，只有跑在浏览器进程内的扩展能合法读取。

## 已知坑 / 边界

- 扩展仍固定连接 8080；开发实例改端口时使用扫码登录。
- 扫码结果仍需四平台真实账号验收；自动化验证生命周期和界面交互，不能替代手机扫码。
- 登录态有效期（本机 profile 实测 cookie 标称）：抖音 `sessionid` ≈ 58 天、知乎 `z_c0` ≈ 178 天、
  小红书 `web_session` ≈ 332 天；实际使用会不断刷新，通常更久。
- worker 里 **CDP 模式被显式关掉**（`ENABLE_CDP_MODE=False`、`CDP_CONNECT_EXISTING=False`），
  所以「连到已打开的浏览器」这条路当前是关的（`tools/cdp_browser.py` 有实现可参考）。
- 换账号不会隔离：应用自己的 profile 是「一个平台一个目录」，同一台机器换账号会覆盖同一份 profile。

## 测试怎么跑

- 后端：`tests/test_xhs_session_restore.py`、`tests/test_xhs_account_verification.py`、
  `tests/test_session_snapshot_lifecycle.py`、`tests/test_extension_security.py`、
  `tests/test_extension_runtime.py`、`tests/test_account_coordinator.py`、`tests/test_account_sync_timings.py`
- 前端：`webui/tests/accountBulkSync.test.ts`、`accountGate.test.ts`、`accounts.test.ts`、
  `extensionSync.test.ts`、`useAccountsOptions.test.ts`
- 扫码回归：`tests/test_worker_login_done.py`、`tests/test_qrcode_popup.py`、`webui/tests/scanLogin.test.ts`；跨页轮询见 `scripts/favorites_ui_smoke.py`。
