# 中文社交平台聚合搜索

本项目是一个面向小红书、抖音、B 站和知乎的跨平台聚合搜索工具。输入一次关键词，即可在一个结果页中查看统一的搜索结果、摘要、排序和跨平台内容分组。

## 快速开始

```shell
uv sync
uv run playwright install chromium
uv run uvicorn api.main:app --host 127.0.0.1 --port 8080
```

前端开发或构建：

```shell
cd webui
npm ci
npm run dev       # 开发模式
npm run build     # 生产构建
```

更多产品说明、支持平台、账号说明和许可证限制请参阅仓库根目录的 [README](../README.md)。

浏览器/CDP、代理和手机号登录说明仍保留在本目录中；这里不再维护旧的 standalone crawler、评论采集、文件存储或数据库使用方式。
