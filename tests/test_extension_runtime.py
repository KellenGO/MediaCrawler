# -*- coding: utf-8 -*-
"""Extension runtime tests: execute the PRODUCTION browser_extension JS in a
Node vm with minimal browser stubs.

Two classes of regression:
1. content_script.js must run in a Content Script environment — which has NO
   importScripts (that API is Service Worker / Worker only). The manifest
   injects ["sync_protocol.js", "content_script.js"] in order, and the two
   files share the globalThis.MCSyncProtocol namespace. Running the two
   production files in a bare vm context reproduces the environment exactly.
2. service_worker.js must pick the cookie store by sender.tab.id →
   getAllCookieStores()[].tabIds match. tabs.Tab has NO cookieStoreId
   property; reading one would silently fall back to stores[0]. The store
   selection is asserted behaviourally: which storeId reaches cookies.getAll.

All cookies used here are fictional.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_NODE = shutil.which("node")
requires_node = pytest.mark.skipif(_NODE is None, reason="node not installed")

# Fictional cookie for the store-selection tests — never a real session.
_FAKE_COOKIE = [{
    "name": "web_session", "value": "fictitious-value-000", "domain": ".xiaohongshu.com",
    "path": "/", "httpOnly": True, "secure": True, "sameSite": "no_restriction",
    "session": True, "storeId": "store-profile-2",
}]

_DRIVER = r"""
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const syncPath = path.join('browser_extension', 'sync_protocol.js');
const syncSrc = fs.readFileSync(syncPath, 'utf8');
const csSrc = fs.readFileSync(path.join('browser_extension', 'content_script.js'), 'utf8');
const swSrc = fs.readFileSync(path.join('browser_extension', 'service_worker.js'), 'utf8');
const input = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));

async function main() {
  const out = { errors: [], mode: input.mode };
  try {
    if (input.mode === 'content-script') {
      const listeners = [];
      const posted = [];
      const sandbox = {
        console: console,
        setTimeout: setTimeout,
        clearTimeout: clearTimeout,
        chrome: {
          runtime: {
            getManifest: function () { return { version: input.manifestVersion }; },
            sendMessage: function (msg, cb) {
              out.sent = msg;
              cb({ success: true, verified: true, safe_error_code: '',
                   safe_message: 'ok', sync_stage: 'completed',
                   received_cookie_count: 1, accepted_cookie_count: 1,
                   skipped_cookie_count: 0, rejected_cookie_count: 0,
                   required_cookie_present: true });
            },
          },
        },
      };
      sandbox.window = {
        addEventListener: function (t, fn) { if (t === 'message') { listeners.push(fn); } },
        postMessage: function (m) { posted.push(m); },
      };
      sandbox.globalThis = sandbox;
      const ctx = vm.createContext(sandbox);
      // No importScripts exists in this context — a Content Script
      // environment has none. sync_protocol.js runs FIRST (manifest
      // content_scripts[0].js order), then content_script.js.
      vm.runInContext(syncSrc, ctx);
      vm.runInContext(csSrc, ctx);
      out.ready = posted.find(function (m) { return m && m.type === 'content-script-ready'; }) || null;
      out.listenerCount = listeners.length;
      // 页面侧对 ready/pong 的版本判定（与 AccountsPage.tsx 的
      // versionAtLeast 生产逻辑一致）：协议版本 2 且扩展版本 ≥ 1.1.3
      // 才视为可用 —— 低于 1.1.3 的旧脚本必须能被区分出来。
      function pageDeemsUsable(msg) {
        if (!msg || msg.extension_protocol_version !== 2) return false;
        const v = String(msg.extension_version || '');
        const parts = v.split('.').map(function (s) { return parseInt(s, 10) || 0; });
        const min = [1, 1, 3];
        for (let i = 0; i < 3; i++) {
          if ((parts[i] || 0) !== min[i]) return (parts[i] || 0) > min[i];
        }
        return true;
      }
      out.pageDeemsReadyUsable = pageDeemsUsable(out.ready);
      if (listeners.length) {
        listeners[0]({ source: sandbox.window, data: { source: 'mc-accounts', type: 'ping' } });
        out.pong = posted.filter(function (m) { return m && m.type === 'pong'; }).pop() || null;
        out.pageDeemsPongUsable = pageDeemsUsable(out.pong);
        listeners[0]({ source: sandbox.window, data: { source: 'mc-accounts', type: 'sync-request',
          ticket: 'tk-1', platform: 'xhs', request_id: 'req-1' } });
        out.response = posted.filter(function (m) { return m && m.type === 'sync-response'; }).pop() || null;
      }
    } else if (input.mode === 'sw-store' || input.mode === 'sw-incognito'
               || input.mode === 'sw-no-store') {
      const getAllCalls = [];
      const getAllStoreCalls = [];
      const stores = input.stores || [];
      const cookiesToReturn = input.cookies || [];
      const sandbox = {
        console: console,
        setTimeout: setTimeout,
        clearTimeout: clearTimeout,
        chrome: {
          cookies: {
            getAllCookieStores: async function () {
              getAllStoreCalls.push(1);
              return stores;
            },
            getAll: async function (opts) { getAllCalls.push(opts); return cookiesToReturn; },
          },
          storage: {
            local: {
              get: async function (k) { return {}; },
              set: async function () { return undefined; },
            },
          },
          runtime: {
            lastError: null,
            onMessage: { addListener: function (fn) { out.listener = fn; } },
          },
        },
      };
      sandbox.globalThis = sandbox;
      sandbox.importScripts = function (file) {
        if (file === 'sync_protocol.js') { vm.runInContext(syncSrc, ctx); }
      };
      const ctx = vm.createContext(sandbox);
      vm.runInContext(swSrc, ctx);
      out.listenerRegistered = typeof out.listener === 'function';
      const listener = out.listener;
      let fetchInfo = null;
      sandbox.fetch = async function (url, opts) {
        fetchInfo = { url: url, headers: opts.headers, body: JSON.parse(opts.body) };
        return { ok: true, status: 200,
                 json: async function () {
                   return { success: true, verified: true, safe_error_code: '',
                            safe_message: 'ok', sync_stage: 'completed',
                            received_cookie_count: 1, accepted_cookie_count: 1,
                            skipped_cookie_count: 0, rejected_cookie_count: 0,
                            required_cookie_present: true, browser_cookie_store_count: stores.length };
                 } };
      };
      let resolveResp;
      const respPromise = new Promise(function (res) { resolveResp = res; });
      // sender.tab carries the REAL incognito flag (chrome.runtime message
      // sender semantics) — the CookieStore fixtures have no incognito field.
      const sender = { tab: { id: input.tabId,
                              incognito: input.incognito === true,
                              url: input.tabUrl || 'http://127.0.0.1:8080/' } };
      const keep = listener({ type: 'sync', ticket: 'tk-1', platform: 'xhs',
                              requestId: 'req-1' }, sender, function (r) { resolveResp(r); });
      out.keepChannel = keep === true;
      out.response = await respPromise;
      out.getAllCalls = getAllCalls;
      out.getAllStoreCalls = getAllStoreCalls;
      out.fetchInfo = fetchInfo;
    } else {
      throw new Error('unknown mode ' + input.mode);
    }
  } catch (e) {
    out.errors.push(String((e && e.stack) || e));
  }
  process.stdout.write(JSON.stringify(out));
}

main();
"""


def _run_driver(payload: dict) -> dict:
    payload_file = Path(os.environ.get("TEMP", ".")) / (
        "mc_runtime_payload_%d.json" % abs(hash(json.dumps(payload, sort_keys=True))))
    payload_file.write_text(json.dumps(payload), encoding="utf-8")
    try:
        proc = subprocess.run(
            [_NODE, "-e", _DRIVER, str(payload_file)],
            cwd=str(_PROJECT_ROOT), capture_output=True, text=True,
            timeout=60, encoding="utf-8")
        assert proc.returncode == 0, proc.stderr
        return json.loads(proc.stdout)
    finally:
        try:
            payload_file.unlink()
        except OSError:
            pass


# ── Problem 1: content script runs WITHOUT importScripts ─────────────────

@requires_node
def test_content_script_runs_without_importscripts():
    """The PRODUCTION content_script.js must load in a bare Content Script
    environment (no importScripts): no ReferenceError, listener registered,
    ready/ping/sync all work through the MCSyncProtocol namespace."""
    out = _run_driver({"mode": "content-script", "manifestVersion": "1.1.3"})
    assert out["errors"] == [], out["errors"]
    assert out["listenerCount"] == 1
    assert out["ready"] is not None
    assert out["ready"]["extension_protocol_version"] == 2
    # Round 10: ready carries the REAL manifest version from the page-visible
    # chrome.runtime.getManifest() — the page can tell which script is live.
    assert out["ready"]["extension_version"] == "1.1.3"
    # ping -> pong carries the protocol version
    assert out["pong"] is not None
    assert out["pong"]["extension_protocol_version"] == 2
    assert out["pong"]["extension_version"] == "1.1.3"
    assert out["pageDeemsReadyUsable"] is True
    assert out["pageDeemsPongUsable"] is True
    # sync-request -> chrome.runtime.sendMessage({type:"sync", ...})
    assert out["sent"]["type"] == "sync"
    assert out["sent"]["ticket"] == "tk-1"
    assert out["sent"]["platform"] == "xhs"
    assert out["sent"]["requestId"] == "req-1"
    # worker result -> sync-response back to the page, request_id preserved
    assert out["response"] is not None
    assert out["response"]["request_id"] == "req-1"
    assert out["response"]["success"] is True
    assert out["response"]["platform"] == "xhs"


# ── Round 10: the page can distinguish 1.1.2 (old script) from 1.1.3 ─────

@requires_node
def test_page_distinguishes_old_and_new_extension_versions():
    """PRODUCTION content_script.js with manifest 1.1.2 vs 1.1.3 must put
    the REAL version in ready/pong. The page-side check (protocol==2 AND
    version >= 1.1.3) must accept 1.1.3 and reject 1.1.2 — protocol version
    alone (2) cannot tell them apart."""
    new_out = _run_driver({"mode": "content-script", "manifestVersion": "1.1.3"})
    assert new_out["errors"] == [], new_out["errors"]
    assert new_out["ready"]["extension_version"] == "1.1.3"
    assert new_out["pong"]["extension_version"] == "1.1.3"
    assert new_out["pageDeemsReadyUsable"] is True
    assert new_out["pageDeemsPongUsable"] is True

    old_out = _run_driver({"mode": "content-script", "manifestVersion": "1.1.2"})
    assert old_out["errors"] == [], old_out["errors"]
    assert old_out["ready"]["extension_version"] == "1.1.2"
    assert old_out["pong"]["extension_version"] == "1.1.2"
    # Same protocol version 2, but the page must reject the old script.
    assert old_out["pong"]["extension_protocol_version"] == 2
    assert old_out["pageDeemsReadyUsable"] is False
    assert old_out["pageDeemsPongUsable"] is False


# ── Problem 2: cookie store selected by sender.tab.id, never stores[0] ───

# Real Chrome CookieStore shape: id + tabIds ONLY — no incognito field
# (incognito lives on the message SENDER's tab, sender.tab.incognito).
_STORES_TWO = [
    {"id": "store-regular-1", "tabIds": [1, 2, 3]},
    {"id": "store-profile-2", "tabIds": [7, 8]},
]


@requires_node
def test_sw_selects_store_by_sender_tab_id():
    """Regular window (sender.tab.incognito=false): the tab belongs to the
    SECOND cookie store — the storeId passed to cookies.getAll must be that
    store's id, not a silent stores[0] fallback."""
    out = _run_driver({"mode": "sw-store", "stores": _STORES_TWO,
                       "tabId": 8, "incognito": False, "cookies": _FAKE_COOKIE})
    assert out["errors"] == [], out["errors"]
    assert out["listenerRegistered"] is True
    assert out["keepChannel"] is True
    assert out["getAllStoreCalls"] == [1]
    assert out["getAllCalls"] == [{"domain": "xiaohongshu.com", "storeId": "store-profile-2"}]
    assert out["response"]["success"] is True
    # request body went through the production chrome-v1 builder
    body = out["fetchInfo"]["body"]
    assert body["cookie_format"] == "chrome-v1"
    assert body["extension_protocol_version"] == 2
    assert body["cookies"][0]["name"] == "web_session"


@requires_node
def test_sw_rejects_incognito_tab_before_any_cookie_access():
    """sender.tab.incognito=true must be rejected at the message entry:
    ZERO calls to getAllCookieStores, cookies.getAll AND fetch — the
    CookieStore fixtures carry no incognito field (the real API has none),
    so a store-based check would be reading an undefined flag."""
    out = _run_driver({"mode": "sw-incognito", "stores": _STORES_TWO,
                       "tabId": 8, "incognito": True, "cookies": _FAKE_COOKIE})
    assert out["errors"] == [], out["errors"]
    assert out["getAllStoreCalls"] == [], (
        "incognito path must not call getAllCookieStores")
    assert out["getAllCalls"] == [], "incognito path must not call cookies.getAll"
    assert out["fetchInfo"] is None, "incognito path must not fetch the backend"
    assert out["response"]["safe_error_code"] == "incognito_store_rejected"
    assert out["response"]["safe_message"] == "无法同步隐身窗口中的登录会话，请使用常规窗口的登录账号"


@requires_node
def test_sw_no_matching_store_returns_cookie_store_not_found():
    """The tab id matches no store — explicit error, never stores[0]."""
    out = _run_driver({"mode": "sw-no-store", "stores": _STORES_TWO,
                       "tabId": 999, "incognito": False, "cookies": _FAKE_COOKIE})
    assert out["errors"] == [], out["errors"]
    assert out["getAllStoreCalls"] == [1]
    assert out["getAllCalls"] == []
    assert out["response"]["safe_error_code"] == "cookie_store_not_found"
