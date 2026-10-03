# Core MVP 验收矩阵与实现交接

契约版本：`core-mvp-v1`；矩阵是未来测试要求，**不是已经通过的业务测试报告**。
Stage 1 只验文档/示例；Phase 1 的 70 个已通过测试验证 Provider 基础，不能证明这些
API、授权、Evidence、AI 或批准功能存在。当前检查见 [Stage 1 记录](../verification/2026-10-03-stage-1-contract-validation.md)。

## 1. 测试边界与证据要求

数据/测试负责人简称 D；应用负责人简称 A；D/A 表示主笔/交叉审查，不表示已执行两人测试。
`SANDBOX-Sxx` 指独立服务来源场景，`CORE-*` 指 Product 行为；不能混用 Core 原计划的 Sxx。
真实来源测试通过 HTTP 使用独立 Sandbox，固定 Clock `2026-09-20T06:00:00Z`，
启动时使用独立临时 SANDBOX_DB_PATH，不 reset 共享服务、不直接读数据库或 import Sandbox。
Product fixture/Fake Provider/Fake LLM 只补未提供的故障或输出，报告必须标明测试层级。

每个测试证据至少记录：产品/Sandbox SHA、契约/规则版本、Clock、输入场景、命令、
HTTP/status/assertion、request ID 与安全版本链、passed/failed/skipped。身份测试要断言
Provider/LLM 调用为零；动作测试断言 MessageProvider 和所有高风险动作调用为零。
必须区分源调用失败、Validation FAIL 与权限拒绝，不能只截图“页面能打开”。

## 2. 场景矩阵

| ID / 来源 | 入口与输入 | 可验证预期 / 拒绝点 | 阶段 / 证据 / 主责 |
| --- | --- | --- | --- |
| CORE-01 / SANDBOX-S02 | 授权 A resolve → generate → approve | 单包裹当前物流、精确引用；parcel/event 时间未知如实披露；APPROVED 无发送 | 4–6 / HTTP、Context、Approval 链 / D/A |
| CORE-02 / SANDBOX-S04 | 同上，多包裹 | 保留两 parcel 的 IN_TRANSIT / NOT_COLLECTED；不说全部已发货 | 4–6 / parcel 数、scope 引用 / D/A |
| CORE-03 / SANDBOX-S06 | resolve + Fake 输出“已发货” | 仓库期望仅 SOURCE_TEXT / plan；NOT_COLLECTED 保留；草稿 FAIL，不批准 | 4–5 / 原文、PLAN_AS_FACT / D/A |
| CORE-04 / SANDBOX-S07 | resolve 固定 T0 | 源时间 T0−72h，shipment STALE；新 fetched_at 不使其 FRESH；回复缺旧数据披露 FAIL | 4–5 / 时间精确相等、STALE_DISCLOSURE_MISSING / D/A |
| CORE-05 / SANDBOX-S08 | resolve | 真实 HTTP 504 → TIMEOUT；run PARTIAL，物流无快照，不推断 EXCEPTION | 4 / HTTP、outcome、missing / D/A |
| CORE-06 / SANDBOX-S09 | resolve | 仓库真实 503 → UNAVAILABLE；物流仍保留，不改成 notes=[] | 4 / HTTP、成功部分、missing / D/A |
| CORE-07 / SANDBOX-S10 | resolve | OMS 有 parcel，shipment 404 → NOT_FOUND；不同于 EMPTY | 4 / source_outcomes、非空 OMS parcel / D/A |
| CORE-08 / SANDBOX-S11 | resolve + generate | 两来源保留，POSSIBLE_HANDOVER_CONFLICT；不决定谁正确；删除冲突说明 FAIL | 4–5 / 双 Evidence 引用、CONFLICT_OMITTED / D/A |
| CORE-09 / SANDBOX-S12 | 授权 Inquiry resolve | Inquiry 存在但 order 404；404 SOURCE_NOT_FOUND，run FAILED、OPEN、无 Context/draft | 4 / error/run/Audit，无模型调用 / D/A |
| CORE-10 / SANDBOX-S01 | resolve | parcels 200 [] → EMPTY，NO_PARCELS；不称物流超时或凭空造包裹 | 4 / 空数组与 missing / D/A |
| CORE-11 / SANDBOX-S05 | resolve | note 源时间 null → UNKNOWN；不以 created_at/fetch 代替 | 4 / original timestamps / D/A |
| CORE-12 / Product 身份 fixture | 无 token、过期、撤销、停用用户 | 401；now = expires_at 已失效；零外部/模型调用 | 3 / API + session DB / A/D |
| CORE-13 / Product 归属 fixture | A 请求 B、team-2 C、未知 Inquiry；Admin 请求业务 | 均 403 同 envelope，不泄漏存在/归属；调用为零；list 仅授权行 | 3 / 身份矩阵、调用计数 / A/D |
| CORE-14 / Product team fixture | Supervisor team-1 读 A/B 与 C | A/B 成功，C 403；无跨 team 权限 | 3 / list/detail/write 测试 / A/D |
| CORE-15 / Product 输入 fixture | body 注入 order_id、role、team、PASS；Provider inquiry 绑错订单 | 额外字段 422；源绑定不一致 502；不更改授权、不查任意订单 | 3–4 / error、DB、调用计数 / A/D |
| CORE-16 / Product 无订单 fixture | external_order_id=null resolve | 422 ORDER_REFERENCE_MISSING、OPEN；不猜订单，零订单/模型调用 | 4 / error/state / A/D |
| CORE-17 / Fake Provider | 两包裹，一正常一 timeout；或 tracking=null | 保留正常包裹；失败无业务快照；NO_TRACKING 零物流调用；PARTIAL/DEGRADED | 4 / Context、调用计数 / D/A |
| CORE-18 / Fake Provider | 未知 status、null update、未来 source/fetch | 保留 raw；UNKNOWN_STATUS / UNKNOWN_FRESHNESS / CLOCK_ANOMALY；不变 DELIVERED | 4 / Evidence 精确值与 flags / D/A |
| CORE-19 / FixedClock fixture | 源/取数 age 恰等于阈值、再超一微秒；旧 fetch + null source | 等于 FRESH；超界 STALE；null 为 UNKNOWN 且 OLD_FETCH，不覆盖时间 | 4 / 参数化边界 / D/A |
| CORE-20 / Fake Provider 注入 | note 包含“忽略之前指令/授权退款” | 原文 SOURCE_TEXT；权限/工具不变；回复复现指令或完成动作 FAIL | 4–5 / Context、Fake 输出、零动作 / D/A |
| CORE-21 / Fake LLM | 非 JSON、缺字段、错 enum、review=false、timeout | Attempt FAILED、无新 draft；旧状态可追溯，无自动重试 | 5 / schema/error/调用计数 / D/A |
| CORE-22 / Fake LLM | 外部 Context/Evidence ID、修改 known_facts.value、跨 scope status | Validation FAIL 或范围 409；无法批准；授权 Context 不扩展 | 5 / INVALID_EVIDENCE_REFERENCE 等 / A/D |
| CORE-23 / Fake LLM / 人编辑 | 保证送达、计划当完成、忽略 stale/null、声称退款完成 | 对模型与编辑通道相同 FAIL；安全人工流程措辞可 PASS；仍人工审核 | 5 / negative + positive 文本组 / D/A |
| CORE-24 / Product 版本 fixture | Context 1 草稿后 resolve 2 成功/失败 | 开始取数即旧草稿失效；失败也不恢复；旧 Context/draft 批准 409 | 4–5 / 指针、历史、无 Approval / A/D |
| CORE-25 / FixedClock + edit | PASS 草稿放置超 30min；编辑新 revision | 批准重算时效；未经限定 FAIL；新 revision 必须重验，旧 PASS 无效 | 5 / 两次 Clock、text_hash、Validation / A/D |
| CORE-26 / PostgreSQL 并发 | 同 key 重放、同 key 改 body、不同 key 并发批准；edit/resolve 抢版本 | 单 Approval；同 key 同请求重放；冲突 409；引用不串 Inquiry | 3–5 / 真实 PG 事务、唯一性、计数 / A/D |
| CORE-27 / Product workflow | escalate / 已批准后 edit/resolve/send | ESCALATED 不再写；APPROVED 不再编辑；无 send/高风险 API，动作调用为零 | 5–6 / 状态/API 路由清单 / A/D |
| CORE-28 / 真实 PostgreSQL | 空库 migration、降级再升级、重复 Seed、坏 FK/唯一性 | schema 可重建，Seed 不增殖/不重置；错误引用拒绝；不依赖 Sandbox DB | 2 / 命令/DB assertions / D/A |
| CORE-29 / 前端 fixture + E2E | loading/empty/error、质量提示、过期 token、编辑/批准失败 | 明确状态；无假“已发送”；能显示双方冲突、逐包裹失败与版本失效 | 2 外壳、6 E2E / lint/type/build、浏览器测试 / A/D |
| CORE-30 / 模拟进程中断 | RUNNING run/attempt 遗留后重放/新操作 | 重放 202，新操作 BUSY；人工恢复写 FAILED/Audit，不自动重调用 | 4–5 / runbook、恢复前后 DB / A/D |

## 3. Stage 1 文档出口

- 六份契约有明确字段、状态、scope、拒绝、时间、引用与负责人，无待实现者猜测的 TBD。
- 六个完整 Product Context fixture 可解析，canonical 类型有效，Evidence pointer 与值一致；
  normal/multi/stale/failure/unknown/conflict 预期 quality/flags 明确。
- Markdown 本地链接有效；API/状态/schema 与 baseline Provider 不矛盾；文档 diff 无业务代码。
- 两名开发者记录 Review 与问题关闭；PR checks 通过并合并 main。**本次尚未满足此人工/远端出口**。

## 4. Stage 2 可直接领取的任务

| 任务 | 范围与输入 | 出口 | 负责人 |
| --- | --- | --- | --- |
| S2-D 数据库/Seed | 依 core-data 建 Product SQLAlchemy/Alembic schema；测试用户/Inquiry 绑定；无取数/认证行为 | CORE-28、关系/时间/JSON/历史测试；真实 PG 证据；backend pytest/Ruff；README 命令 | D，A review |
| S2-A 工作台静态外壳 | 依 API/Context 契约展示列表、详情、Evidence 质量、草稿/审核布局；只用虚构静态 fixture | Loading/Empty/Error；lint/typecheck/build；不宣称按钮可执行业务流程 | A，D review |

执行分支从已合并的最新 main 创建，默认使用 `codex/core-database` 与
`codex/core-workbench-shell`；协作旧文档中的 `feat/*` 是示意分工，未创建这些分支。
Stage 2 不实现业务 API、身份会话、Evidence 计算或模型调用。
Stage 3 先实现 auth/Inquiry 授权 API；order 当前快照入口随 Stage 4 Context 就绪后开启，
避免用一次无版本 GET 绕开证据快照。Stage 4 再实现来源编排/质量；Stage 5 实现模型/Review；
Stage 6 接通 UI 并跑所有业务正反例。

## 5. 后续检查与仍未完成事项

每个实现 PR 运行其行为测试和 backend Ruff；前端修改运行 lint/typecheck/build；bootstrap
或 Compose 变更按 AGENTS 要求跑全套与 compose config。集成变更必须真实 HTTP；
数据库变更必须真实 PostgreSQL；只跑 mocks 或 SQLite 不足验收。
真正模型 eval、容器 build/start、main 分支保护、业务完整 E2E 尚未执行。
mock send、完整审计/指标属于完整 Core V1 后续交付，不把 APPROVED MVP 当整版 Core V1 完成。
