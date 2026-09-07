# 分批探索实现方案

- 默认每轮每个平台 20 条，单轮最大 40 条；同一主题每个平台累计最多 100 条原始来源，每个主题最多 20 轮（空轮也计入）。
- 换一批延续各平台页码/偏移和搜索标识；刷新从头开始。每个平台每次操作最多 4 次列表请求，各页串行，保留现有等待。分页期间禁用列表调用的隐式重试；登录预检、签名准备和摘要补全不计入这 4 次列表预算。
- 后端维护当前主题的进度、已返回 ID、剩余页内结果和轮次。浏览器只提交上一任务 ID；拒绝过期/重复继续请求。新主题替换旧主题，旧请求不能推进新主题。
- 完整页面未用完的结果保存在后端，下一轮先消费它们，不能跳过页尾。失败/取消保留最后已确认的进度；冷却平台不推进。
- 跨轮按平台 ID 去重，再用现有跨平台规则合并。新来源属于旧内容时更新旧轮卡片；已有轮次可回看，收藏独立保留。
- 首轮缓存连同分页状态一起保存；后续轮次不覆盖首轮缓存。账号变化后拒绝继续旧主题，需从头刷新。
- 界面默认仅保留“换一批”；按需展开轮次回看与刷新操作。展示新增数量、重复过滤、分页请求数、更多内容状态及累计上限。
- 验证：四平台分页/页尾缓存、跨轮分组、重复继续、部分失败、取消、冷却、缓存隔离、数量限制、浏览器换批及收藏保留。真实平台额度仍需日常低频验证，不宣称这些参数为风控安全额度。

## 已完成的行为与边界

普通搜索使用当前数量设置，已有自定义值保持不变；恢复默认后为 20 条/平台。“换一批”只取未展示的来源，不通过打乱原结果制造新内容。同一内容后续出现其他平台版本时补充到原轮卡片，渐进展示期间也会过滤这种旧内容。

“更多”提供刷新与轮次回看，完成新任务后自动收起。刷新从头开始一个主题，可能再次取得旧内容。轮次和分页进度仅保存在当前后端内存，页面刷新可以恢复；新搜索或重启后端会结束原主题。收藏、备注仍使用原来的浏览器本地存储，换批不会清除它们。当前主题内的单平台失败重试也延续该平台位置，结果作为新一轮保留。

4 次限制只统计搜索列表调用。列表调用内的自动重试已关闭，显式风控状态会立即停止当前平台并进入现有冷却流程。登录预检、签名准备、摘要补全及浏览器资源请求不包含在这个数字内。结果不足可能来自平台返回量、重复过滤、分页预算、累计数量上限或轮次上限，不能保证每轮都凑满设定数量，也不能由本地速度推断平台安全额度。

历史轮次中的平台状态与完成时间保留当轮快照；卡片可能包含后续轮次补充的平台版本。尚未进行真实账号的高频或大批量压力测试。

## 改动文件

| 文件 | 改动目的 |
| --- | --- |
| `aggregate_search/pagination.py`（新增） | 四平台分页、页内剩余内容、请求预算、重复过滤和搜索限流判定。 |
| `aggregate_search/models.py` | 统一数量边界及后端到 worker 的分页参数。 |
| `aggregate_search/provider_chain.py` | 支持按错误与剩余预算阻止回退。 |
| `aggregate_search/worker.py` | 为单次请求绑定独立分页状态，传输检查点并清理新增路径使用的客户端。 |
| `api/schemas/search.py` | 20/40 数量规则、继续搜索请求和探索信息响应。 |
| `api/services/search_exploration.py`（新增） | 当前主题累计上限、轮次、跨轮分组、历史回看。 |
| `api/services/search_job_manager.py` | 继续请求校验、取消恢复、缓存隔离、进度接收和摘要副本同步。 |
| `api/services/result_cache.py` | 首轮缓存同时保存分页位置与未展示的页尾内容。 |
| `media_platform/xhs/core.py` | 聚合搜索委托分页引擎；普通爬虫保持原路径。 |
| `media_platform/douyin/core.py` | 同上。 |
| `media_platform/bilibili/core.py` | 同上。 |
| `media_platform/xhs/client.py` | 分页请求期间关闭隐式重试，提前识别 HTTP 风控状态。 |
| `media_platform/zhihu/client.py` | 同上。 |
| `media_platform/bilibili/client.py` | 同上。 |
| `media_platform/douyin/client.py` | 分页请求提前识别 HTTP 风控状态。 |
| `webui/src/types/search.ts` | 分页探索、轮次和请求类型。 |
| `webui/src/lib/platformLimits.ts` | 默认 20、最大 40，保留现有自定义值。 |
| `webui/src/hooks/useAggregateSearch.ts` | 传递上一任务标识，等待后端完成轮次整理后再停止轮询。 |
| `webui/src/hooks/useSearchExperience.ts` | 换批、主题刷新、单平台续搜和真实终态接线。 |
| `webui/src/lib/searchExperience.ts` | 取消且本轮没有内容时仍保留可继续的主题身份与历史。 |
| `webui/src/components/search/SearchPage.tsx` | 换批入口、按需展开的刷新/回看、累计信息及历史展示。 |
| `webui/src/components/search/SearchBar.tsx` | 数量上限提示更新。 |
| `webui/src/components/accounts/AccountsPage.tsx` | 数量控制注释同步为 40；控件本身复用公共常量。 |
| `tests/test_search_exploration.py`（新增） | 20 项分页、worker、续搜、缓存、取消、冷却、账号边界回归测试。 |
| `tests/test_aggregate_search_models.py` | 更新模型默认值及越界断言。 |
| `tests/test_platform_limits.py` | 更新数量越界断言。 |
| `webui/tests/platformLimits.test.ts` | 更新默认数量与上下界断言。 |
| `scripts/search_exploration_smoke.py`（新增） | 隔离浏览器验证换批、旧轮版本、收藏、刷新恢复、耗尽与窄屏。 |
| `docs/search-exploration-plan.md`（新增） | 方案、边界、文件清单及验证记录。 |

## 验证结果（2026-09-07）

- 完整 Python 回归：775 passed，8 skipped，4 subtests passed。包括上述新增 20 项测试。
- 前端测试：219 passed。
- TypeScript 与 Vite 生产构建：通过，已生成本地 `webui/dist`。
- 三套隔离浏览器验收通过：`search_exploration_smoke.py`、`result_library_smoke.py`、`search_stability_smoke.py`。包括 320/390 像素宽度、原收藏/备注/导出行为、冷却和统计面板。
- `git diff --check`：通过。

首次定向测试遇到默认临时目录权限问题，改用项目内独立临时目录后完整回归通过。现有非阻断告警仍有 FastAPI 生命周期弃用提示、缓存清理协程告警，以及前端 Browserslist 数据陈旧和大 chunk 提示。本次未新增依赖、数据库变更、提交或推送。
