# 桌面 BAT 启动器：DeepSeek dsh web

日期：2026-08-14

## 目标

在桌面创建一个 BAT 脚本，双击即可启动 `npx @deepseek-ai/dsh web`（DeepSeek 官方 CLI "dsh" 的 Web 模式）。

## 文件位置与命名

- 桌面：`C:\Users\Kellen\Desktop\启动 DeepSeek dsh.bat`
- 该文件不属于 MediaCrawler 项目，仅在桌面独立存在

## 行为设计

双击后：

1. 在 BAT 自身窗口内直接运行命令（用户已确认，不弹新窗口）
2. `chcp 65001` 保证中文提示不乱码；文件以 UTF-8 保存
3. 检查 `npx` 是否存在；不存在则输出中文错误提示并暂停（防窗口闪退）
4. 运行 `npx --yes @deepseek-ai/dsh web`（`--yes` 跳过首次安装确认）
5. 命令退出后显示"按任意键关闭窗口"，窗口保留以便查看输出/报错

## 验收标准

- 双击桌面图标后 BAT 窗口打开，dsh web 正常启动
- 首次运行无需手动确认 npx 安装
- 命令退出或报错时窗口不闪退，能看到原因
- 中文提示无乱码

## 不做的事（YAGNI）

- 不做端口健康检查 / 自动开浏览器（用户未选该方案）
- 不检查 Node 版本，仅检查 npx 是否可用
- 不添加任何第三方依赖
