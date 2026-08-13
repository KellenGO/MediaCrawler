# 桌面 BAT 启动器：DeepSeek dsh web 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在桌面创建 `启动 DeepSeek dsh.bat`，双击即可在窗口内运行 `npx --yes @deepseek-ai/dsh web`。

**Architecture:** 单文件 BAT，无任何依赖。`chcp 65001` + UTF-8 保证中文不乱码；`where npx` 检查环境；`npx --yes` 跳过安装确认；`pause` 防止闪退。

**Tech Stack:** Windows 批处理脚本（cmd），无第三方依赖。

## Global Constraints

- 文件保存路径：`C:\Users\Kellen\Desktop\启动 DeepSeek dsh.bat`（在项目仓库之外，无需 git 提交）
- 文件编码：UTF-8（无 BOM）——Write 工具默认编码，与脚本内 `chcp 65001` 配合
- 脚本内容必须与 spec（`docs/superpowers/specs/2026-08-14-deepseek-dsh-launcher-design.md`）一致：
  - 窗口内直接运行（不弹新窗口）
  - 检查 npx，缺失时输出中文错误并暂停
  - 使用 `npx --yes`
  - 退出后 `pause` 保留窗口

---

### Task 1: 创建并验证桌面 BAT 脚本

**Files:**
- Create: `C:\Users\Kellen\Desktop\启动 DeepSeek dsh.bat`

**Interfaces:**
- 无（独立单文件，不与其他任务交互）

- [ ] **Step 1: 写入脚本文件**

用 Write 工具创建 `C:\Users\Kellen\Desktop\启动 DeepSeek dsh.bat`（UTF-8 无 BOM），内容：

```bat
@echo off
chcp 65001 >nul
title DeepSeek dsh web
cd /d "%~dp0"

rem 检查 npx 是否可用
where npx >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 npx，请先安装 Node.js：https://nodejs.org/
    pause
    exit /b 1
)

rem --yes 跳过 npx 首次运行时的安装确认
npx --yes @deepseek-ai/dsh web

echo.
echo dsh 已退出，按任意键关闭窗口...
pause
```

- [ ] **Step 2: 验证文件存在且内容正确**

- Read 工具读取该文件，逐行核对：`chcp 65001`、`where npx` 检查、`npx --yes @deepseek-ai/dsh web`、结尾 `pause` 均存在。
- 确认路径 `C:\Users\Kellen\Desktop\启动 DeepSeek dsh.bat` 存在。
- 不做活体运行测试：`dsh web` 是交互式/常驻进程，从本会话启动会阻塞且干扰用户环境；实际双击验证由用户在桌面完成（预期：窗口打开 → dsh 启动 → 退出后窗口保留）。

- [ ] **Step 3: 提交计划文档（仅仓库内文件）**

```bash
git add "docs/superpowers/plans/2026-08-14-deepseek-dsh-launcher.md"
git commit -m "docs: add implementation plan for desktop DeepSeek dsh launcher"
```
