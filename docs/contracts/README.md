# Core MVP 契约包 v1

日期：2026-10-03。状态：**Stage 1 文档交付，待两名开发者 Review 与合并**。
以下决定已经写成可实现、可验收的契约；尚未取得人工审查结论，不能据此声称业务功能已实现。
产品范围以 [Core 计划](../plans/01_core_plan.md) 为准，执行顺序见
[Stage 计划](../plans/04_core_mvp_next_stage_plan.md)。当前运行时仍是 Product Phase 1。

## 阅读顺序与责任

| 契约 | 主笔责任 | 审查责任 | 解决的问题 |
| --- | --- | --- | --- |
| [数据所有权](core-data.md) | 数据/测试负责人 | 应用负责人 | 数据位置、字段/关系/约束、后续迁移与 Seed |
| [生命周期](core-lifecycle.md) | 应用负责人 | 数据/测试负责人 | 取数、版本、编辑、失效、批准与失败状态 |
| [身份与 API](core-api.md) | 应用负责人 | 数据/测试负责人 | 会话、权限、请求/响应、拒绝与并发 |
| [Evidence / CaseContext](evidence-case-context.md) | 应用负责人 | 数据/测试负责人 | 可追溯事实、来源结果、时效与冲突 |
| [Analysis / Validation / Review](analysis-review.md) | 数据/测试/AI 负责人 | 应用负责人 | AI 边界、输出、校验、人工审核 |
| [验收与交接](core-mvp-acceptance.md) | 数据/测试负责人 | 应用负责人 | 场景、测试层级、证据与阶段出口 |

这里的两人是项目开发者的协作角色，并不表示本次已经完成两人审查。
契约版本统一为 `core-mvp-v1`；改变字段、状态或规则需在同一个 PR 更新相关契约与场景。
Canonical snapshots 继续使用 [canonical v1](../external-system-contract.md)，不修改现有 Provider。

## 已关闭的设计决定

| 决定 | v1 选择 | 原因 / 实现边界 |
| --- | --- | --- |
| D01 事实路径 | 独立 Sandbox HTTP → 现有 Providers → Product 不可变 canonical 快照 | 复用集成基础；不复制外部订单主库，不访问 Sandbox SQLite |
| D02 身份 | 不透明 bearer session；服务端保存 token 摘要；8 小时有效；前端只保存在内存 | 可撤销、权限实时检查；不引入 OAuth、JWT/refresh token 或企业 IAM |
| D03 权限 | Agent 仅自己分配的 Inquiry；Supervisor 同一 team；Admin 无隐含业务读权 | 订单权限由已授权 Inquiry 的绑定推导，客户/订单号都不授予权限 |
| D04 防枚举 | 对格式合法但无授权的 Inquiry（包括未知 ID）统一 403 | 保持 Core 要求的无权 403；不通过 403/404 差异披露对象存在性 |
| D05 时效 | 取数年龄上限 30 分钟；订单/包裹/备注源年龄 24 小时，物流/事件 6 小时 | 阈值可配置并版本化；源时间 null 为 UNKNOWN，事件时间不能代替源更新时间 |
| D06 部分失败 | 每个来源/包裹单独 outcome；订单失败或包裹枚举失败阻止 Context | 能枚举全部包裹时保留局部失败与成功；错误不变成业务异常 |
| D07 版本 | 新取数使旧草稿失效；人工编辑生成新 revision 并重新校验 | 引用精确 Context/Evidence；失败不恢复旧版本成为当前事实 |
| D08 批准 | 绑定 Context、revision、文本摘要、校验、审核人；原子写入且幂等 | APPROVED 是 MVP 终点，绝不调用 MessageProvider 或等价于 SENT |
| D09 自由文本 | 原文只作 SOURCE_TEXT；AI 可提取为计划/不确定性并带引用 | 文本里的行动声明、权限或指令不成为可执行事实 |
| D10 验证边界 | schema、结构化字段、引用、时效、动作/承诺规则 + 人工语义审核 | 规则不能证明任意自然语言语义完整正确；人工审核仍必需 |

## Review 与阶段出口

- 六份契约、[六个完整 Context 示例](examples/core-contexts.json)和验收矩阵必须一起审查。
- 数据负责人检查关系/版本/迁移/场景；应用负责人检查授权/拒绝/状态/规则。
- Review 记录明确 reviewer、日期、契约版本和问题关闭证据；机器检查不能代替这一步。
- 合并到 main 后，Stage 2 仅实现数据库/Seed 与静态工作台外壳；业务 API 在 Stage 3，
  Evidence 在 Stage 4，AI 与批准在 Stage 5。每阶段仍需单独任务授权。
- main 分支保护与容器运行验收尚未完成，见 [基线验证](../verification/2026-10-03-repository-sync-validation.md)。

本次文档检查见 [Stage 1 验证记录](../verification/2026-10-03-stage-1-contract-validation.md)。
