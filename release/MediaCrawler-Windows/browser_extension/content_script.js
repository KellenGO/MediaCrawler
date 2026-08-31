/**
 * MediaCrawler 会话同步助手 — content script
 *
 * 只注入到 http://127.0.0.1:8080/* 和 http://localhost:8080/*。
 * 只做两件事：
 *   1. 接收本地网站页面通过 window.postMessage 发来的同步请求
 *      （仅 ticket / platform / request_id 三个值）；
 *   2. 转发给 service worker，并把 service worker 的安全结果
 *      （success/platform/verified/safe_error_code/safe_message）
 *      回传页面。
 *
 * Cookie 绝不经过这里、绝不经过 window.postMessage 回传页面。
 */

// sync_protocol.js 由 manifest 的 content_scripts[0].js 数组先行注入
// （见 manifest.json），本脚本直接读取其全局命名空间。
// Content Script 环境没有 importScripts —— 绝不能在这里调用它。

const PROTOCOL = globalThis.MCSyncProtocol;
const VALID_PLATFORMS = ["xhs", "douyin", "bilibili", "zhihu"];

// 扩展实际版本 —— 只来自 chrome.runtime.getManifest().version，绝不手写
// 重复常量（manifest 是唯一事实来源）。网页据此区分 1.1.2（Round 8 旧
// 脚本）与 1.1.3（当前）—— 仅协议版本无法区分。
function extensionVersion() {
  try {
    const m = chrome.runtime.getManifest();
    return (m && typeof m.version === "string") ? m.version : "";
  } catch (e) {
    return "";
  }
}

window.addEventListener("message", (event) => {
  if (event.source !== window) {
    return; // 只接受同页面消息
  }
  const msg = event.data;
  if (!msg || typeof msg !== "object" || msg.source !== "mc-accounts") {
    return;
  }
  if (msg.type === "ping") {
    // 页面用 ping 探测扩展是否已注入；带协议版本（兼容判断）与
    // 实际扩展版本（区分 1.1.2 旧脚本 vs 1.1.3 当前脚本）。
    window.postMessage({
      source: "mc-accounts",
      type: "pong",
      extension_protocol_version: PROTOCOL.EXTENSION_PROTOCOL_VERSION,
      extension_version: extensionVersion(),
    }, "*");
    return;
  }
  if (msg.type !== "sync-request") {
    return;
  }
  const { ticket, platform, request_id } = msg;
  if (typeof ticket !== "string" || !ticket ||
      !VALID_PLATFORMS.includes(platform)) {
    window.postMessage({
      source: "mc-accounts-response",
      type: "sync-response",
      request_id: typeof request_id === "string" ? request_id : "",
      success: false,
      platform: platform || "",
      verified: false,
      safe_error_code: "sync_ticket_invalid",
      safe_message: "同步请求参数无效",
    }, "*");
    return;
  }

  chrome.runtime.sendMessage(
    { type: "sync", ticket, platform, requestId: request_id },
    (result) => {
      const r = result || {};
      window.postMessage({
        source: "mc-accounts-response",
        type: "sync-response",
        request_id: typeof request_id === "string" ? request_id : "",
        success: Boolean(r.success),
        platform,
        verified: Boolean(r.verified),
        safe_error_code: r.safe_error_code || "",
        safe_message: r.safe_message || "",
        sync_stage: r.sync_stage || "",
        status: r.status || "",
        received_cookie_count: (typeof r.received_cookie_count === "number")
          ? r.received_cookie_count : null,
        accepted_cookie_count: (typeof r.accepted_cookie_count === "number")
          ? r.accepted_cookie_count : null,
        skipped_cookie_count: (typeof r.skipped_cookie_count === "number")
          ? r.skipped_cookie_count : null,
        required_cookie_present: (typeof r.required_cookie_present === "boolean")
          ? r.required_cookie_present : null,
        // 只透传白名单 marker 的布尔值（由 sync_protocol.js 的
        // parseSyncResponse 裁剪），绝不包含任何 Cookie 值。
        login_marker_presence: (r.login_marker_presence
          && typeof r.login_marker_presence === "object")
          ? r.login_marker_presence : null,
      }, "*");
    }
  );
});

// 页面用于检测扩展是否已安装/注入；带协议版本与实际扩展版本，页面
// 据此判断是否过旧（低于 1.1.3 → 提示重新加载扩展，禁止同步）。
window.postMessage({
  source: "mc-accounts",
  type: "content-script-ready",
  extension_protocol_version: PROTOCOL.EXTENSION_PROTOCOL_VERSION,
  extension_version: extensionVersion(),
}, "*");
