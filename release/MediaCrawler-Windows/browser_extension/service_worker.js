/**
 * MediaCrawler 会话同步助手 — service worker (MV3)
 *
 * Cookie wire contract v2: raw Chrome cookies, whitelisted to the chrome-v1
 * fields, are sent to the backend EXACTLY ONCE with cookie_format
 * "chrome-v1". The backend performs the single Chrome -> Playwright mapping.
 * This worker never pre-converts (no expires / no uppercase sameSite),
 * never writes cookie values to storage, never sends cookies to web pages,
 * and never logs cookie values.
 */

importScripts("sync_protocol.js");

const PROTOCOL = globalThis.MCSyncProtocol;

const API_ORIGIN = "http://127.0.0.1:8080";
const API_ROOT = API_ORIGIN + "/api/search/accounts";

// 与后端 accounts service 保持一致的平台 → 官方域名映射。
const PLATFORM_DOMAINS = {
  xhs: "xiaohongshu.com",
  douyin: "douyin.com",
  bilibili: "bilibili.com",
  zhihu: "zhihu.com",
};

/** 构造同步结果对象 —— 仅安全字段，绝不包含 cookie 值。 */
function safeResult(overrides) {
  return Object.assign({
    ok: true,
    success: false,
    verified: false,
    status: "",
    safe_error_code: "",
    safe_message: "",
    sync_stage: "",
    received_cookie_count: null,
    accepted_cookie_count: null,
    skipped_cookie_count: null,
    browser_cookie_store_count: null,
  }, overrides || {});
}

/**
 * 读取指定平台 Cookie（仅该平台官方域）。
 * 通过发起同步的 tab 的归属 cookie store 读取（sender.tab.id →
 * getAllCookieStores().tabIds 匹配），避免误读其他 profile 的 store；
 * tabs.Tab 没有 cookieStoreId 属性，绝不能从 sender.tab 读 store id。
 * 隐身窗口已在 onMessage 中由 sender.tab.incognito 拒绝（CookieStore 没有
 * incognito 字段，读它永远是 undefined）；找不到归属 store 时明确报错，
 * 绝不静默回退到 stores[0]。
 * 返回 { cookies, skippedPartitioned, storeCount, storeId } 或 { error }。
 */
async function readPlatformCookies(platform, tabId) {
  const domain = PLATFORM_DOMAINS[platform];
  if (!domain) {
    return { error: safeResult({ safe_error_code: "sync_ticket_invalid",
      safe_message: "不支持的平台" }) };
  }

  let stores = [];
  try {
    stores = await chrome.cookies.getAllCookieStores();
  } catch (e) {
    stores = [];
  }
  const storeCount = stores.length;
  let store = null;
  if (typeof tabId === "number") {
    store = stores.find((s) => Array.isArray(s.tabIds)
      && s.tabIds.indexOf(tabId) !== -1) || null;
  }
  if (!store) {
    return { error: safeResult({ safe_error_code: "cookie_store_not_found",
      safe_message: "无法确定该页面所属的 cookie store，请刷新页面后重试",
      browser_cookie_store_count: storeCount }) };
  }
  const targetStoreId = store.id;
  const storeIdShort = String(targetStoreId || "").slice(0, 12);

  let all = [];
  try {
    const opts = { domain };
    if (targetStoreId) opts.storeId = targetStoreId;
    all = await chrome.cookies.getAll(opts);
  } catch (err) {
    // chrome.runtime.lastError 兜底捕获（callback 风格遗留错误）
    let detail = "";
    if (chrome.runtime.lastError) {
      detail = String(chrome.runtime.lastError.message || "");
    }
    console.error("[sync] read cookies failed", err && err.message, detail);
    return { error: safeResult({ safe_error_code: "extension_cookie_read_failed",
      safe_message: "读取浏览器 Cookie 失败，请重新加载扩展后重试",
      browser_cookie_store_count: storeCount }) };
  }

  const cookies = [];
  let skippedPartitioned = 0;
  for (const c of all) {
    if (c && c.partitionKey) {
      skippedPartitioned += 1; // partitioned cookie 仅计数，绝不发送
      continue;
    }
    cookies.push(c);
  }
  return { cookies, skippedPartitioned, storeCount,
    storeId: targetStoreId, storeIdShort };
}

async function handleSync({ ticket, platform, requestId, tabId }) {
  if (typeof ticket !== "string" || !ticket) {
    return safeResult({ safe_error_code: "sync_ticket_invalid",
      safe_message: "缺少一次性同步票据" });
  }
  if (!(platform in PLATFORM_DOMAINS)) {
    return safeResult({ safe_error_code: "sync_ticket_invalid",
      safe_message: "不支持的平台" });
  }

  const read = await readPlatformCookies(platform, tabId);
  if (read.error) {
    return read.error;
  }
  if (!read.cookies.length) {
    return safeResult({ safe_error_code: "browser_cookie_not_found",
      safe_message: "当前浏览器没有读取到该平台的登录 Cookie，"
        + "请确认已在扩展所在浏览器的账号中登录平台官网",
      browser_cookie_store_count: read.storeCount });
  }

  // chrome-v1 请求体：字段白名单由 sync_protocol.js 统一裁剪。
  const body = PROTOCOL.buildSyncBody({
    platform,
    cookies: read.cookies,
    requestId,
    skippedPartitioned: read.skippedPartitioned,
    storeCount: read.storeCount,
  });

  let resp;
  try {
    resp = await fetch(`${API_ROOT}/${platform}/sync`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Sync-Ticket": ticket,
      },
      body: JSON.stringify(body),
    });
  } catch (e) {
    return safeResult({ safe_error_code: "platform_api_error",
      safe_message: "无法连接本地服务（127.0.0.1:8080），请确认网站后端已启动",
      browser_cookie_store_count: read.storeCount });
  }

  let data = {};
  try {
    data = await resp.json();
  } catch (e) {
    data = {};
  }
  // 结构化错误优先，旧版 {detail} 兜底（兼容解析）。
  const parsed = PROTOCOL.parseSyncResponse(data);
  const result = Object.assign(
    safeResult({
      ok: resp.ok,
      http_status: resp.status,
      platform,
      request_id: requestId || "",
      browser_cookie_store_count: read.storeCount,
    }),
    parsed,
  );
  // 非 2xx 但响应体无结构化错误时，仍让页面看到明确失败。
  if (!resp.ok && !result.safe_error_code) {
    result.safe_error_code = "sync_http_error";
    result.safe_message = result.safe_message || `同步请求失败（HTTP ${resp.status}）`;
  }

  // 只保存非敏感元数据 —— 绝不保存 cookie 值。
  try {
    const key = `sync:${platform}`;
    const all = await chrome.storage.local.get(key);
    all[key] = {
      lastSyncAt: Date.now(),
      success: result.success,
      verified: result.verified,
      status: result.status,
      http_status: resp.status,
      safe_error_code: result.safe_error_code,
      safe_message: result.safe_message,
      sync_stage: result.sync_stage,
      received_cookie_count: result.received_cookie_count,
      accepted_cookie_count: result.accepted_cookie_count,
      skipped_cookie_count: result.skipped_cookie_count,
      browser_cookie_store_count: result.browser_cookie_store_count,
      store_id_short: read.storeIdShort || "",
    };
    await chrome.storage.local.set(all);
  } catch (e) {
    // storage 失败不影响本次同步结果
  }
  return result;
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg !== "object" || !sender.tab) {
    return false;
  }
  if (msg.type === "sync") {
    // content script 只存在于 localhost 页面，URL 校验兜底。
    const url = String(sender.tab.url || "");
    if (!url.startsWith("http://127.0.0.1:8080") && !url.startsWith("http://localhost:8080")) {
      sendResponse(safeResult({ ok: false, safe_error_code: "sync_ticket_invalid",
        safe_message: "仅允许从本地网站发起同步" }));
      return false;
    }
    // 隐身窗口在入口直接拒绝：sender.tab.incognito 是 chrome.runtime 消息
    // 的正式隐身标志（CookieStore 只有 id/tabIds，没有 incognito 字段）。
    // 此路径绝不调用 getAllCookieStores / cookies.getAll / fetch。
    if (sender.tab.incognito === true) {
      sendResponse(safeResult({ ok: false, safe_error_code: "incognito_store_rejected",
        safe_message: "无法同步隐身窗口中的登录会话，请使用常规窗口的登录账号" }));
      return false;
    }
    // 用发起同步的 tab id 在其归属 cookie store 中读取，避免误读其他
    // profile（tabs.Tab 没有 cookieStoreId 属性）。
    const tabId = (typeof sender.tab.id === "number") ? sender.tab.id : null;
    handleSync({ ticket: msg.ticket, platform: msg.platform,
      requestId: msg.requestId, tabId }).then(sendResponse);
    return true; // 保持消息通道直到 sendResponse 被调用
  }
  if (msg.type === "get-status") {
    // 供 popup 查询最近同步状态（只读元数据，无 cookie）。
    chrome.storage.local.get(null).then((all) => {
      const out = {};
      for (const p of Object.keys(PLATFORM_DOMAINS)) {
        const s = all[`sync:${p}`] || {};
        out[p] = {
          has_sync: Boolean(s.lastSyncAt),
          lastSyncAt: s.lastSyncAt || null,
          success: Boolean(s.success),
          verified: Boolean(s.verified),
          status: s.status || null,
          safe_error_code: s.safe_error_code || null,
          sync_stage: s.sync_stage || null,
          received_cookie_count: (typeof s.received_cookie_count === "number")
            ? s.received_cookie_count : null,
          accepted_cookie_count: (typeof s.accepted_cookie_count === "number")
            ? s.accepted_cookie_count : null,
          browser_cookie_store_count: (typeof s.browser_cookie_store_count === "number")
            ? s.browser_cookie_store_count : null,
          store_id_short: s.store_id_short || null,
        };
      }
      sendResponse({ ok: true, platforms: out });
    });
    return true;
  }
  return false;
});
