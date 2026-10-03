# Stage 1 契约文档检查记录

日期：2026-10-03（Asia/Shanghai）。用户授权“现在开始进行下一阶段”，依当前执行计划
交付 Core MVP Stage 1 文档契约，不开始 Stage 2 数据库/工作台实现。
分支：`docs/core-mvp-contracts`；HEAD 仍为 `0d04cfc`，本次交付为本地未提交文档。
远端/运行时基线与上一轮结果见 [仓库同步验证](2026-10-03-repository-sync-validation.md)。

## 交付与关闭的设计

[契约索引](../contracts/README.md)连接六份契约：数据所有权、生命周期、身份/API、
Evidence/CaseContext、Analysis/Validation/Review、验收矩阵。D01–D10 固定事实路径、
session/team、403 防枚举、时效、局部失败、版本、幂等与不可信文字处理。
补充 [完整 Product Context 示例](../contracts/examples/core-contexts.json)，包含六种质量场景；
它们是虚构 Product fixture，不冒充真实 Sandbox 响应。
README、architecture、scope、核心计划、Stage 计划、协作设计及 AGENTS 同步状态。
没有修改 backend、frontend、依赖、Compose、CI、Provider 或 Sandbox 文件。

## 已执行的文档验证

运行方式：PowerShell here-string 传入 `./backend/.venv/Scripts/python.exe -`，
使用 Python 标准库及现有 `app.integrations.models`，设置 `PYTHONDONTWRITEBYTECODE=1`。
只验证文档数据，不新建业务实现或永久测试工具。

| 检查 | 结果 | 实际范围 |
| --- | --- | --- |
| 六个完整 JSON Context | PASS，6 / 6 | NORMAL、MULTI_PARCEL、STALE、SOURCE_FAILURE、UNKNOWN_TIME、CONFLICT |
| Canonical 类型 | PASS，33 条记录 | 现有 Pydantic Order/Parcel/Shipment/Note/SupportInquiry 的 model_validate_json，封闭字段与 UTC |
| Evidence 引用 | PASS，34 条 | SHA-256 身份、snapshot version、JSON Pointer、原始类型/值、来源 ID、源/抓取/事件时间逐项相等 |
| 质量与失败 | PASS | 独立按 Clock/阈值核算 FRESH/STALE/UNKNOWN；验证 quality/flags、双包裹、失败无伪造快照 |
| 引用分组 | PASS | facts / source_texts 按 kind 分组，order/parcel/unknown/missing/conflict 引用全部存在，冲突至少两个 ID |
| 负例检查 | PASS | 无效 pointer 触发 KeyError；TIMEOUT fetch_id 不在成功快照集合 |
| JSON 文档代码块 | PASS，7 个 | core-api 的请求/响应/错误与 Analysis 字段示意可解析；占位 ID 明确为示意，非实际输出 |
| 文档链接与结构 | PASS，17 份 Markdown、63 个本地链接 | 目标存在，代码围栏配对，六份契约版本相同；无未决 TODO 字段 |
| 验收编号 | PASS，CORE-01–CORE-30 | 30 个不同且连续的 Product 场景，明确真实 HTTP / Product fixture / Fake LLM |
| 交付范围与空白检查 | PASS | git diff --check 无错误；backend/frontend/CI/Compose/env template 的 diff 为空 |

Markdown 本地链接、矩阵编号、契约状态/策略版本与 git diff 范围另外机械检查。
具体命令为 `git diff --check`、`git status --short`、
`git diff --name-only -- backend frontend .github compose.yaml .env.example`，
以及 Python 扫描本次契约/关联文档的 Markdown 链接与 CORE-01–CORE-30 编号。

## 校核中修正的两处差异

- 真实 S02 parcel/event 的 source_updated_at 为 null；传输 SUCCEEDED 不代表质量 COMPLETE。
  API 例子明确 DEGRADED，Context 示例 NORMAL 使用有已知时间的 Product fixture。
- 真实 S11 备注是 `Parcel has not been handed to the carrier today.`；规则覆盖带 `the`
  的原文，不再依赖漏词的短语。仅为 POSSIBLE_HANDOVER_CONFLICT，不判定哪一方正确。

## 检查边界与未完成出口

本次未改运行时，未重复运行上一轮已经通过的 70 个 backend tests、前端 lint/type/build
或真实 HTTP 测试；那些结果仍只证明同一 Phase 1 代码，详见上次记录。
文档示例机械验证不等于 Stage 4 Evidence 实现测试或 Stage 5 模型评估通过。
30 项业务验收矩阵是未来实现要求，当前无业务 routes、数据库模型、AI 或批准行为。

两名开发者 Review、PR 创建/checks/合并、main 分支保护、容器 build/start 尚未完成；
本次没有 commit/push/合并，没有启动 Stage 2，没有把“文档成稿”称作整个阶段人工验收通过。
Stage 2 的可领取任务与出口见 [验收与交接](../contracts/core-mvp-acceptance.md)。
