import tseslint from 'typescript-eslint'

// 前端 lint 的第一版配置。
//
// 背景：`package.json` 里一直有 `"lint": "eslint ."`，但 devDependencies 里没有 eslint，
// CI（ci.yml）也只能打印 "skipping lint" —— 一个悬空脚本，给人「我们 lint 过了」的错觉。
// 这一版先把这个错觉消掉：只启用 typescript-eslint 的 recommended，且不把任何规则升级为
// 阻断项之外的额外负担；真正想收紧时再往 rules 里加，不要一上来就开满。
export default tseslint.config(
  {
    ignores: [
      'dist/**',
      'node_modules/**',
      'run-compiled-tests.mjs',
      'vite.config.ts',
    ],
  },
  ...tseslint.configs.recommended.map((config) => ({
    ...config,
    files: ['src/**/*.{ts,tsx}'],
  })),
  {
    files: ['src/**/*.{ts,tsx}'],
    rules: {
      // any 在这份代码里用得不少，一次性清完不现实，先不拦。
      '@typescript-eslint/no-explicit-any': 'off',
      // TS 编译器本身会报错，eslint 再报一遍是噪音。
      'no-undef': 'off',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
)
