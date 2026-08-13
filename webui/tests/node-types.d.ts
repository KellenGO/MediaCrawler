/**
 * 最小 node:test 类型声明（Round 12 测试用）。
 * 不引入 @types/node 依赖；仅覆盖本测试套件用到的 API。
 */

declare module "node:test" {
  export interface TestContext {
    [key: string]: unknown;
  }
  export function test(
    name: string,
    fn: (t: TestContext) => void | Promise<void>
  ): void;
}

declare module "node:assert/strict" {
  interface AssertFn {
    (value: unknown, message?: string): void;
    ok(value: unknown, message?: string): void;
    equal(actual: unknown, expected: unknown, message?: string): void;
    notEqual(actual: unknown, expected: unknown, message?: string): void;
    deepEqual(actual: unknown, expected: unknown, message?: string): void;
    fail(message?: string): void;
  }
  const assert: AssertFn;
  export default assert;
}
