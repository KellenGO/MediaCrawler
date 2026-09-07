import { test } from "node:test";
import assert from "node:assert/strict";
import { cooldownSeconds } from "../src/lib/statusDisplay.js";

test("冷却秒数向上取整，到期和未知截止时间不锁定旧版本结果", () => {
  const now = Date.parse("2026-09-06T12:00:00Z");
  assert.equal(cooldownSeconds("2026-09-06T12:00:00.001Z", now), 1);
  assert.equal(cooldownSeconds("2026-09-06T12:01:00Z", now), 60);
  assert.equal(cooldownSeconds("2026-09-06T12:00:00Z", now), 0);
  assert.equal(cooldownSeconds("2026-09-06T11:59:00Z", now), 0);
  for (const deadline of [undefined, null, "", "invalid"]) assert.equal(cooldownSeconds(deadline, now), 0);
});
