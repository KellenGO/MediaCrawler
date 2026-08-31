export interface EnvironmentHealth {
  status: "ok";
  environment_status: "ok" | "degraded";
  backend_available: boolean;
  version: string;
  api_version: string;
  web_version: string | null;
  version_match: boolean | null;
  browser_available: boolean;
  browser_backend: string | null;
  redis_required: boolean;
  redis_available: boolean | null;
}

/** Keep the frontend/API compatibility check separate from backend liveness. */
export function environmentHealthWarning(
  health: EnvironmentHealth | false | null,
): string | null {
  if (health === false) return "本地后端不可用，请先启动后端服务。";
  if (!health) return null;
  if (health.version_match === false || typeof health.version !== "string") {
    return "前后端版本不匹配，请重新构建前端后刷新页面。";
  }
  if (health.browser_available === false) {
    return "浏览器不可用，请安装 Chrome/Edge，或执行 playwright install chromium。";
  }
  if (health.redis_required && health.redis_available === false) {
    return "当前配置需要 Redis，但 Redis 暂不可用。";
  }
  return null;
}
