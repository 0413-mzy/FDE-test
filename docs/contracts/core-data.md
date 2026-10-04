# Core MVP 数据所有权与持久化契约

契约版本：`core-mvp-v1`。状态及审查要求见 [索引](README.md)。这是后续实现的设计，
本阶段不创建 SQLAlchemy 模型、迁移、数据库连接或 Seed 命令。

## 1. 所有权与事实路径

Product PostgreSQL 只持有用户权限、咨询工作流，以及本次处理依据的不可变历史快照。
订单、包裹、物流、仓库备注仍由独立外部系统拥有；读取只能经过现有 Provider 协议。
不用订单/客户主表复制 Sandbox；订单 items、包裹、事件保存在 canonical JSON 中。
这只是完整 Core V1 数据模型在 MVP 中的存储裁剪，不删除 Core V1 的后续需求。

| 信息 | 原始拥有者 | Product 使用方式 |
| --- | --- | --- |
| 订单/包裹/物流/备注 | 外部系统 | 验证 canonical snapshots 后追加版本；禁止覆盖源时间/状态 |
| 外部 Inquiry ID、问题和源创建时间 | MessageProvider | 经授权的固定绑定读取；保存本次 question 快照 |
| Inquiry 的 team、assignee、订单绑定 | Product | Seed 或后续受控导入设置；客户端/AI/外部 order_id 不能改归属 |
| fetched_at、取数结果、Evidence、Context | Product 程序 | Clock 与确定性规则生成，保留历史版本 |
| Analysis、回复措辞 | AI 输出 / 人工编辑 | 记录版本与校验，不写外部业务事实 |
| Approval、Audit | Product 程序和已认证审核人 | 绑定最终版本；不等于发送或业务执行 |

MVP 不提供导入、分配、换绑订单、管理用户或重新打开已批准咨询的 API。
Seed 只生成虚构用户、team、咨询绑定，不凭外部事实新建授权关系。
测试 Fake Provider 也必须返回现有 canonical 类型；不从仓储层注入“最新事实”。

## 2. 类型与共同规则

- 内部主键为 UUID，由 Product 生成；API 示例中的 `inq-002` 等是阅读别名，实际请求用 UUID。
- 外部 ID 为保留原值的非空字符串，与 `source_system` 联合解释；禁止按相同字符串跨来源关联。
- 时间采用 PostgreSQL `timestamptz`，API 用 UTC `Z`；所有 Product 时间来自注入的 Clock。
- 下表 `?` 是 required nullable 字段；缺键与 null 不等价。未写 `?` 的字段非空。
- JSON 使用 JSONB，遵守对应契约的封闭字段集合；schema_version 必须随记录保存。
- 原文/回复不 trim、不改换行。摘要为原始 UTF-8 字节 SHA-256 小写 hex；摘要不是权限凭据。
- 工作流行带 `lock_version`（正整数）做并发检查；不可变记录不能以 UPDATE 修补历史事实。
- 外键默认 RESTRICT；MVP 无删除历史接口。写入、版本切换、Audit 必须同事务提交。

## 3. 最小逻辑记录

下列是可直接落地的逻辑实体。`SourceFetch` 内嵌快照，`ContextVersion` 内嵌 Evidence，
不要求拆出 Order/Parcel/Evidence 主表；避免为 JSON 检索提前增加数据同步机制。
阶段实现须保留这些逻辑约束，即使映射为不同物理表也必须在契约 PR 中说明。

| 记录 | 必需字段（除 id 外） | 拥有者与用途 |
| --- | --- | --- |
| Team | code、display_name、created_at | Product；单一客服组边界，非租户 |
| User | username、password_hash、role、team_id?、is_active、created_at、lock_version | Product；role = AGENT / SUPERVISOR / ADMIN |
| AuthSession | user_id、token_digest、created_at、expires_at、revoked_at? | Product；撤销/过期；从不保存明文 token |
| Inquiry | source_system、external_inquiry_id、external_order_id?、team_id、assigned_agent_id、state、escalation_reason?、latest_run_id?、current_context_id?、current_draft_id?、lock_version、created_at、updated_at | Product；绑定权限与当前指针；升级原因仅授权详情可读 |
| ResolutionRun | inquiry_id、actor_id、idempotency_key、request_hash、version、state、request_id、started_at、finished_at?、error_code? | Product；一次手动取数，不含自动重试 |
| SourceFetch | run_id、operation、target_id、outcome、request_id、started_at、completed_at、fetched_at?、error_code?、source_system、canonical_payload? | Product；一个 Provider 操作；成功 payload = `{records: [...]}` |
| ContextVersion | inquiry_id、run_id、version、schema_version、policy_version、created_at、quality、payload | Product；包含 Evidence 与授权范围的不可变 Context |
| GenerationAttempt | inquiry_id、context_id、actor_id、idempotency_key、request_hash、state、request_id、started_at、finished_at?、error_code?、analysis?、model_metadata? | Product；模型尝试与失败也可审计 |
| DraftRevision | inquiry_id、context_id、generation_attempt_id?、revision、parent_revision_id?、editor_id?、origin、analysis、reply_text、text_hash、created_at | AI/人修改内容，程序存版本；origin = AI / HUMAN |
| ValidationResult | draft_id、context_id、policy_version、validator_version、text_hash、status、errors、warnings、evaluated_at | 程序；status = PASS / FAIL，每次评估单独保存 |
| Approval | inquiry_id、context_id、draft_id、validation_id、reviewer_id、idempotency_key、request_hash、text_hash、approved_at | 人决定、程序约束；MVP 终点 |
| AuditLog | inquiry_id?、actor_id?、event_type、record_id?、request_id、occurred_at、safe_metadata | 程序；状态、失败、修改与批准追踪；不复制问题/回复全文 |

AuthSession 和 GenerationAttempt 等先建 schema，行为分别留到 Stage 3/5。
没有 Send、RetryJob、Cache、Customer/Profile、业务动作表。SourceFetch 就是最小集成日志：
ordinary logs 只输出 operation/outcome/request ID/时间；业务 JSON 放受授权保护的存储中。
Audit.event_type 固定为 LOGIN_SUCCESS / LOGIN_FAILED / LOGOUT / ACCESS_DENIED /
RESOLVE_STARTED / RESOLVE_SUCCEEDED / RESOLVE_PARTIAL / RESOLVE_FAILED /
GENERATION_STARTED / GENERATION_SUCCEEDED / GENERATION_FAILED / DRAFT_EDITED /
VALIDATION_PASSED / VALIDATION_FAILED / APPROVED / ESCALATED / OPERATION_RECOVERED。
safe_metadata 只存内部版本/ID、状态、规则/错误 code 与摘要；原问题、回复、升级原因和源
payload 放专门授权记录，不能复制进 ordinary logs 或 safe_metadata。

## 4. 关系与约束

| 约束 | 正例 | 必须拒绝的反例 |
| --- | --- | --- |
| User.username、Team.code、AuthSession.token_digest 唯一 | 第二次 Seed 更新同一用户 | 重复用户名建立另一个身份 |
| AGENT/SUPERVISOR 必须有 team；ADMIN team_id = null | Agent A 属 team-1 | 无 team Agent、Admin 因有 team 获得业务权 |
| assignee 为同 team 的活跃 AGENT | Inquiry team-1 分配 Agent A | 分配 team-2 Agent 或 Supervisor |
| Inquiry `(source_system, external_inquiry_id)` 唯一 | 已授权 INQ-DEMO-002 读取同一绑定 | 同一外部咨询生成两个权限不同的工作流 |
| Run `(inquiry_id, version)` 与 `(inquiry_id, idempotency_key)` 唯一 | 手动重查 version 2、新 key | 同一 key 不同请求，新建 run |
| 每个 Run 的 `(operation, target_id)` 唯一 | 两个 parcel 各有 get_shipment 结果 | 同包裹失败后在同 run 偷偷重试覆盖 |
| Context.run_id 唯一，`(inquiry_id, version)` 唯一 | PARTIAL run 对应一个 Context | FAILED run 或同 run 生成两份 Context |
| Attempt `(inquiry_id, idempotency_key)` 唯一 | 重放返回已记录失败/成功 | 相同 key 重新调用模型 |
| Draft `(inquiry_id, revision)` 唯一 | 编辑创建 revision 2、parent = 1 | 更新 revision 1 文本保留原批准 |
| 每个 Inquiry 最多一个 Approval；`(inquiry_id, idempotency_key)` 唯一 | 重放完全相同批准返回原对象 | 用新 key 批准不同 revision |
| 当前指针与所有引用必须属于同 Inquiry/run | Draft.context_id 属自身 Inquiry | 引用另一 Agent 的 Context/Evidence |

简单唯一性、非空、enum、外键用 PostgreSQL 约束保证。跨行的同 team、同 Inquiry、
状态与当前版本检查由服务在事务内锁定相关行后执行；不能仅靠前端或先查后写。
用户角色/team 的改变也须遵守同一锁顺序并撤销相应会话，避免授权检查与提交之间换权。
MVP 无这些管理接口，测试仍需能验证活跃身份和团队边界。

SourceFetch 成功为 SUCCESS / EMPTY；payload 非 null，fetched_at 非 null，error_code = null。
EMPTY 仅适用返回数组的 Provider，records = []。失败或 NO_TRACKING 时 payload/fetched_at = null，
completed_at 仍记录操作结束时间；不能把失败结束时间称为“事实抓取时间”。
SupportInquiry 没有 canonical fetched_at；SourceFetch.fetched_at 是 Product 本次成功调用的
元数据，不往 SupportInquiry 增造字段。其他快照/事件内部 fetched_at 保留适配器原值。

## 5. 版本、快照与 Seed

Run.version 从 1 递增；Context.version 等于其 run.version，失败 run 会留下版本空洞。
Evidence.id 在一个 Context 内由 snapshot ID + JSON Pointer 稳定生成，定义见
[Evidence 契约](evidence-case-context.md)。新 run 即使值相同也生成新 Evidence 身份。
批准永远引用完整版本链；禁止对历史 Context 重新填充 fetched_at 后继续批准。

Stage 2 使用 SQLAlchemy 2 + Alembic + PostgreSQL（连接约定 `postgresql+psycopg`）。
迁移只创建 Product schema；空库 upgrade 到 head、降级/再升级与约束测试须在真实 PostgreSQL。
SQLite 不代替 PostgreSQL 迁移、JSONB、唯一性或并发验收。

Seed 使用稳定业务键而非硬编码密码：两个 team、team-1 的 Agent A/B 和 Supervisor、
team-2 的 Agent C、无业务权限的 Admin；将 12 个虚构外部 Inquiry 固定映射为内部绑定。
正常样例分配 A，保留 B/C 越权样例；Seed 只读显式测试配置生成密码哈希，不记录密码，
缺配置即失败；production 不允许运行 demo Seed。重复执行不增殖、不重置既有工作流。
无订单绑定 fixture 单独建立 `external_order_id: null`；不调用所有订单搜索来猜绑定。

## 6. 交接与验收

Stage 2 验证迁移、Seed、唯一性、错误外键、不可变历史和同 Inquiry 引用；Stage 3/5 再验证
授权和并发事务行为。完整场景与负责人见 [验收矩阵](core-mvp-acceptance.md)。
数据负责人交接 schema、迁移、Seed 说明和真实 PostgreSQL 结果；应用负责人依据
[生命周期](core-lifecycle.md)及 [API](core-api.md)实现服务，不从 JSON 快照推导权限。
