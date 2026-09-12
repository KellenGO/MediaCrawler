/**
 * 搜索前的账号操作闸门（Round 18，无 React 依赖）。
 *
 * 背景：账号同步/验证与搜索互斥 —— 它们会打开同一个 persistent browser
 * profile，后端用排他租约保护。打开程序时自动同步登录状态之后，用户可能
 * 立刻发起搜索；若不处理，搜索会撞上 409"账号操作进行中"。
 *
 * 这里不做后端改动：后端在账号操作期间会把平台状态置为 ``syncing`` /
 * ``verifying``，而这两个状态本来就会被账号轮询读到。搜索在真正提交前等
 * 这两个状态消失即可 —— 让搜索等一小会儿，好过直接失败。
 */

/** 账号操作占用共享浏览器 profile 的状态。 */
const BUSY_STATUSES: ReadonlySet<string> = new Set(["syncing", "verifying"]);

/** 搜索等待账号操作的上限；超时后照常提交（409 仍由后端兜底）。 */
export const ACCOUNT_GATE_TIMEOUT_MS = 20000;

/** 闸门轮询间隔。 */
export const ACCOUNT_GATE_POLL_MS = 600;

export interface AccountGateProbe {
  platform: string;
  status: string;
}

/** 是否仍有平台在占用共享 profile（同步/验证中）。 */
export function accountOpsBusy(
  accounts: readonly AccountGateProbe[] | null | undefined
): boolean {
  if (!accounts) return false;
  return accounts.some((a) => BUSY_STATUSES.has(a.status));
}

export interface WaitForAccountOpsIdleOptions {
  timeoutMs?: number;
  pollMs?: number;
  /** 便于测试注入（默认 Date.now / setTimeout）。 */
  now?: () => number;
  sleep?: (ms: number) => Promise<void>;
  /**
   * 每轮读取账号状态；抛异常视为"无法判定"→ 立即放行（失败开放），
   * 绝不因为探测失败而把用户的搜索卡住。
   */
  fetchAccounts: () => Promise<readonly AccountGateProbe[] | null>;
}

/**
 * 等待账号操作结束。返回 true 表示已空闲（可以搜索）；false 表示等到超时。
 *
 * 失败开放：探测异常、或一开始就空闲，都立即返回 true。
 */
export async function waitForAccountOpsIdle(
  options: WaitForAccountOpsIdleOptions
): Promise<boolean> {
  const {
    fetchAccounts,
    timeoutMs = ACCOUNT_GATE_TIMEOUT_MS,
    pollMs = ACCOUNT_GATE_POLL_MS,
    now = () => Date.now(),
    sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms)),
  } = options;

  const deadline = now() + timeoutMs;
  // 先看一次：没有任何账号操作时不引入任何额外延迟。
  for (;;) {
    let busy = false;
    try {
      busy = accountOpsBusy(await fetchAccounts());
    } catch {
      return true; // 读不到状态 → 放行
    }
    if (!busy) return true;
    if (now() >= deadline) return false;
    await sleep(pollMs);
  }
}
