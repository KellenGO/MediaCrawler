// sync_protocol.js — pure functions shared by the service worker and
// content script (loaded via importScripts) and by Node-based wire-contract
// tests (loaded via require). NO chrome.* access, NO I/O: fully testable.
//
// Cookie wire contract (v2):
//   The extension sends RAW Chrome-cookies-API cookies, whitelisted to the
//   chrome-v1 fields below, with cookie_format: "chrome-v1". The backend
//   performs the single Chrome -> Playwright mapping. The extension NEVER
//   pre-converts (no expires, no uppercase sameSite).

'use strict';

const COOKIE_FORMAT_CHROME_V1 = 'chrome-v1';
const EXTENSION_PROTOCOL_VERSION = 2;

// Fields the backend accepts from the Chrome cookies API. Anything else is
// stripped here and rejected by the backend if it still arrives.
const CHROME_V1_FIELDS = [
  'name', 'value', 'domain', 'path', 'expirationDate',
  'httpOnly', 'secure', 'sameSite', 'session', 'storeId',
];

// Whitelist a raw Chrome cookie to the chrome-v1 fields.
// Partitioned cookies are dropped at the source (counted by the caller,
// never sent) — defense in depth, in case a caller forgets to filter.
function toChromeV1Cookie(c) {
  if (!c || c.partitionKey) return null;
  const out = {};
  for (const k of CHROME_V1_FIELDS) {
    if (Object.prototype.hasOwnProperty.call(c, k)) out[k] = c[k];
  }
  return out;
}

// Build the sync POST body. cookie_format is always chrome-v1; the protocol
// version lets the backend/page detect outdated extensions.
function buildSyncBody({ platform, cookies, requestId, skippedPartitioned, storeCount }) {
  return {
    cookie_format: COOKIE_FORMAT_CHROME_V1,
    extension_protocol_version: EXTENSION_PROTOCOL_VERSION,
    cookies: (cookies || []).map(toChromeV1Cookie).filter(Boolean),
    request_id: requestId || '',
    skipped_partitioned: skippedPartitioned || 0,
    browser_cookie_store_count: storeCount || 0,
  };
}

// Login-marker whitelist: marker NAME + presence boolean ONLY — never
// cookie values, never a full cookie list. Mirrors the backend's
// LOGIN_MARKER_NAMES (douyin: LOGIN_STATUS/sessionid/sessionid_ss;
// zhihu: z_c0/d_c0; bilibili: SESSDATA/DedeUserID; xhs: web_session).
const LOGIN_MARKER_WHITELIST = [
  'LOGIN_STATUS', 'sessionid', 'sessionid_ss', 'z_c0', 'd_c0',
  'SESSDATA', 'DedeUserID', 'web_session',
];

// Parse a backend sync response: structured fields first, with a legacy
// {detail: string} fallback. Never exposes cookie values.
function parseSyncResponse(data) {
  const d = (data && typeof data === 'object') ? data : {};
  const legacy = typeof d.detail === 'string' && d.detail ? d.detail : '';
  const num = (v) => Number.isFinite(v) ? v : null;
  // login_marker_presence: pass through only whitelisted marker names with
  // boolean values — nothing else crosses the bridge.
  let loginMarkerPresence = null;
  const rawMarkers = (d.login_marker_presence
    && typeof d.login_marker_presence === 'object') ? d.login_marker_presence : null;
  if (rawMarkers) {
    const out = {};
    let any = false;
    for (const k of LOGIN_MARKER_WHITELIST) {
      if (typeof rawMarkers[k] === 'boolean') { out[k] = rawMarkers[k]; any = true; }
    }
    if (any) loginMarkerPresence = out;
  }
  return {
    success: Boolean(d.success),
    verified: Boolean(d.verified),
    status: (typeof d.status === 'string') ? d.status : '',
    safe_error_code: (typeof d.safe_error_code === 'string' && d.safe_error_code)
      ? d.safe_error_code : '',
    safe_message: (typeof d.safe_message === 'string' && d.safe_message)
      ? d.safe_message : legacy,
    sync_stage: (typeof d.sync_stage === 'string') ? d.sync_stage : '',
    received_cookie_count: num(d.received_cookie_count),
    accepted_cookie_count: num(d.accepted_cookie_count),
    skipped_cookie_count: num(d.skipped_cookie_count),
    rejected_cookie_count: num(d.rejected_cookie_count),
    required_cookie_present: (typeof d.required_cookie_present === 'boolean')
      ? d.required_cookie_present : null,
    login_marker_presence: loginMarkerPresence,
    browser_cookie_store_count: num(d.browser_cookie_store_count),
  };
}

// Shared namespace — the content script and service worker run this file
// FIRST (manifest content_scripts[0].js order / importScripts) and read the
// functions from a single global, exactly like a module. The namespace
// assignment is idempotent, so the same file can also be required by Node
// tests.
const API = globalThis.MCSyncProtocol = (globalThis.MCSyncProtocol || {
  COOKIE_FORMAT_CHROME_V1,
  EXTENSION_PROTOCOL_VERSION,
  CHROME_V1_FIELDS,
  toChromeV1Cookie,
  buildSyncBody,
  parseSyncResponse,
});

// Node test support — inert inside the browser.
if (typeof module !== 'undefined' && module.exports) {
  module.exports = API;
}
