# Findings & Decisions

## Requirements
- 用户输入关键词，同时搜索小红书、抖音、Bilibili、知乎
- 统一展示结果，支持全部/分平台筛选
- 每条结果展示：标题、作者昵称、原平台链接、发布时间、封面、互动数据、平台标识
- 四个平台通过独立 Python 子进程并行搜索
- 前端轮询获取结果
- 单用户、本地使用、不持久化

## Research Findings
- Python 3.14.2 已安装，uv 未安装
- Node.js v24.15.0 和 npm 11.12.1 可用
- 项目 Python 依赖和前端 node_modules 均未安装
- 所有四个平台 crawler/client 代码路径存在且与审计结论一致
- 现有 `api/main.py` 绑定 0.0.0.0，需改为 127.0.0.1
- 现有 `crawler_manager.py` 硬编码 `uv`，且将 cookies 写入命令行参数
- config 模块使用全局变量，多平台并行必须通过子进程隔离
- 现有测试分在 `test/` 和 `tests/` 两个目录

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| sys.executable 启动子进程 | uv 未安装，设计明确要求不使用 uv |
| 四个独立 Python 子进程 | 绕过全局 config 冲突，实现真正并行 |
| stdin/stdout NDJSON 协议 | Windows 命令行转义安全 |
| 内存中 SearchJobManager | MVP 不需要持久化 |
| FastAPI 127.0.0.1 绑定 | 本地单用户使用 |
| 每个平台独立 Playwright persistent profile | 避免并发锁冲突 |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| uv 未安装 | 使用 sys.executable 替代 |
| Python 依赖未安装 | 需先 pip install |

## Resources
- 项目根目录: C:\Users\Kellen\Desktop\MediaCrawler-main
- Python: C:\Users\Kellen\AppData\Local\Programs\Python\Python314\python.exe
- 主要爬虫代码: media_platform/{xhs,douyin,bilibili,zhihu}/
- 现有 API: api/main.py (端口 8080)
- 前端: webui/ (React + Vite + TypeScript)
