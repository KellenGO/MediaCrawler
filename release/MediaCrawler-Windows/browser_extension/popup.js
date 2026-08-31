/**
 * popup：显示扩展状态 + 四个平台最近一次同步结果（仅元数据）。
 * 不读取、不展示任何 Cookie。
 */

const PLATFORM_NAMES = {
  xhs: "小红书",
  douyin: "抖音",
  bilibili: "B站",
  zhihu: "知乎",
};

function browserName() {
  const ua = navigator.userAgent || "";
  if (/Edg\//.test(ua)) return "Edge";
  if (/Chrome\//.test(ua)) return "Chrome";
  return "Chromium";
}

async function refresh() {
  const connEl = document.getElementById("conn");
  const version = chrome.runtime.getManifest().version || "?";
  connEl.textContent = `浏览器：${browserName()} · 扩展版本 ${version}`;
  // 检测本地 API 是否在运行
  try {
    const r = await fetch("http://127.0.0.1:8080/api/health", { method: "GET" });
    const ok = r.ok && (await r.json()).status === "ok";
    connEl.textContent = ok ? "已连接本地网站（127.0.0.1:8080）" : "本地网站 API 未运行";
    connEl.className = "status " + (ok ? "ok" : "bad");
  } catch (e) {
    connEl.textContent = "本地网站 API 未运行";
    connEl.className = "status bad";
  }

  const ul = document.getElementById("platforms");
  ul.textContent = "";
  chrome.runtime.sendMessage({ type: "get-status" }, (resp) => {
    const statuses = (resp && resp.platforms) || {};
    for (const [key, name] of Object.entries(PLATFORM_NAMES)) {
      const li = document.createElement("li");
      const info = statuses[key];
      if (info && info.lastSyncAt) {
        const when = new Date(info.lastSyncAt).toLocaleTimeString();
        const verified = info.verified ? "已验证" : "未验证";
        const counts = (typeof info.received_cookie_count === "number")
          ? ` · 读取 ${info.received_cookie_count} 条`
          : "";
        const stage = info.sync_stage ? ` · ${info.sync_stage}` : "";
        const store = info.store_id_short ? ` · store #${info.store_id_short}` : "";
        li.textContent = `${name}：${info.success ? "同步成功" : "同步失败"}（${when}）`
          + ` · ${verified}${counts}${stage}${store}`;
        if (info.safe_error_code) {
          const sub = document.createElement("div");
          sub.className = "sub";
          sub.textContent = info.safe_error_code;
          li.appendChild(sub);
        }
      } else {
        li.textContent = `${name}：尚未同步`;
      }
      ul.appendChild(li);
    }
  });
}

document.getElementById("open-accounts").addEventListener("click", () => {
  chrome.tabs.create({ url: "http://127.0.0.1:8080/#/accounts" });
});

refresh();
