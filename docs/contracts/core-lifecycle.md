# Inquiry / Context / Draft / Review 生命周期契约

契约版本：`core-mvp-v1`；本阶段只定义行为，未实现工作流。
数据记录见 [core-data](core-data.md)，HTTP 形状见 [core-api](core-api.md)。

## 1. 状态与版本

Inquiry.state = `OPEN | CONTEXT_READY | DRAFTED | APPROVED | ESCALATED`。
APPROVED 与 ESCALATED 为 MVP 终止状态；没有 SENT、自动完成或重新打开入口。
人工拒绝草稿可以继续编辑/重新生成；转人工处理用明确的 escalation 操作。

| 对象 | 状态 | 含义 |
| --- | --- | --- |
| ResolutionRun | RUNNING / SUCCEEDED / PARTIAL / FAILED | 取数进行中 / 全部操作成功 / 可用但来源不完整 / 不能生成 Context |
| GenerationAttempt | RUNNING / SUCCEEDED / FAILED | 一次模型调用；schema 不合法等失败也记录 |
| ValidationResult | PASS / FAIL | 特定 Context、文本、规则与评估时刻的结果 |
| DraftRevision | 不设可改 status | 不可变内容；是否当前/可批准由 Inquiry 指针与 Validation 推导 |

Run.version 单调递增；Context.version 等于 Run.version，失败 run 无 Context。
Draft.revision 在 Inquiry 内单调递增，人工编辑或重新生成都追加 revision。
Context、Evidence、Analysis、Draft、Validation 和 Approval 的旧记录始终可追溯。
读取历史要重新授权；历史版本不能用于新的批准。

## 2. 转移表

所有入口首先检查有效会话和 [Inquiry 权限](core-api.md)。操作者可以是本 Inquiry 的
Agent 或同 team Supervisor；不存在“AI 操作者”。状态检查与写入使用 Inquiry 行锁和
expected_lock_version；同一 Inquiry 不允许两个进行中的取数/生成操作。

| 操作 / 原状态 | 前置条件 | 成功后 | 失败后 |
| --- | --- | --- | --- |
| resolve-context / OPEN、CONTEXT_READY、DRAFTED | 有固定订单绑定；非忙碌；版本匹配 | 开始时清空当前 Context/Draft，OPEN；成功/部分成功设 CONTEXT_READY | 保持 OPEN，FAILED run；不恢复旧指针 |
| generate-draft / CONTEXT_READY、DRAFTED | 当前 Context；无运行中操作；版本匹配 | 新 revision + Validation；设 DRAFTED，即使语义规则 FAIL | 模型或 schema 失败保留原状态/当前 draft；Attempt = FAILED |
| edit-draft / DRAFTED | expected_draft_id 为当前 revision；无运行中操作 | 新 HUMAN revision、重验、DRAFTED | 请求不合法/并发冲突不改原 revision |
| approve / DRAFTED | 当前 Context、当前 draft；重新校验 PASS；版本匹配 | 原子写 Approval/Audit，APPROVED | 409 版本冲突或 422 校验失败；仍 DRAFTED |
| escalate / OPEN、CONTEXT_READY、DRAFTED | 非忙碌；版本匹配；reason 非空 | ESCALATED，保存 Inquiry.escalation_reason 与安全 Audit | 请求失败不改状态 |
| 任何写操作 / APPROVED、ESCALATED | 除已成功操作的同 key 重放 | 409 STATE_CONFLICT | 不调用 Provider/LLM，不改终止结果 |

开始 resolve 的事务先记录 RUNNING、占用该 Inquiry、清除当前指针并递增 lock_version，
再执行 HTTP；结束事务保存结果/Context、释放占用并再次递增 lock_version。
生成同样先记录 Attempt 占用再调用模型，结束后递增 lock_version。编辑、批准和升级
各在一个事务中完成并递增一次。响应必须返回最新 lock_version，客户端不能猜递增次数。
若进程在外部调用中中断，RUNNING 不可被新操作覆盖；GET 显示 BUSY。
MVP 无后台重试/自动恢复。运维只能按人工 runbook 将遗留操作标记 FAILED、写 Audit、释放
占用；若模型结果是否取得不确定，也不得用相同 key 重新调用。恢复测试列入阶段验收。

## 3. 来源失败与 Context 可用性

必须先成功读取与 Product 绑定一致的 SupportInquiry，随后成功读取订单及完整包裹列表。
缺订单绑定 → 422 ORDER_REFERENCE_MISSING；不猜订单、不调用订单 Provider。
SupportInquiry ID/订单绑定不一致 → FAILED / SOURCE_BINDING_MISMATCH；不能更新权限绑定。
订单 404 → FAILED / SOURCE_NOT_FOUND；订单或包裹枚举 timeout/unavailable/invalid → FAILED。
以上都无新 Context，无草稿生成资格；历史事实仅在明确标注的历史视图可看。

已成功枚举所有包裹后，逐包裹物流与仓库查询失败仍保存其 outcome。
有 timeout、unavailable、not-found、invalid、rejected、conflict 或 NO_TRACKING → PARTIAL；
可生成 DEGRADED Context，保留成功部分，列出缺失与限制；不能形成所有包裹均正常的结论。
成功空数组为 EMPTY，属于成功操作，既不代表物流故障，也不证明已发货。
全部操作成功为 SUCCEEDED；旧时间、未知时间或来源冲突不改变传输成功，Context 可为 DEGRADED。

## 4. 并发与幂等

resolve/generate 使用 `Idempotency-Key`（1–200 字符、非空白、保留原值）。
作用域是 `(Inquiry, operation, key)`；request_hash 为 actor_id 与请求 JSON
（递归按键排序、无多余空格、UTF-8、原样保留字符串）的 SHA-256。
同 key 同请求先经当前权限检查，再返回既有操作结果；RUNNING 返回 202 与查询地址。
同 key 不同请求返回 409 IDEMPOTENCY_CONFLICT，不产生第二次调用。
重放校验先于 expected_lock_version，避免正常重放被旧版本拒绝。
已有成功/失败结果均不重新执行；手动重新取数/生成需新 key 和最新版本。

approve 只在成功的原子事务中占用 key 并保存 Approval；请求失败不占用 key。
同 key 同批准请求返回原 Approval（200），即使 Inquiry 已 APPROVED；仍须认证和授权。
同 key 不同请求返回 409 IDEMPOTENCY_CONFLICT；另一个 key 在已批准 Inquiry 返回
409 STATE_CONFLICT。数据库每个 Inquiry 最多一个 Approval，不能靠按钮防双击。
edit/escalate 使用 expected_lock_version/expected_draft_id；第二次重复提交返回 409，
不追加相同文本或第二条终止决定。批准/升级都不调用 MessageProvider。

## 5. Validation 与批准时刻

生成后的 Validation 必须检查整个 Analysis 与 reply_text。人工编辑只改变 reply_text，
analysis.reply_draft 同步为新文本；结构化 Analysis 其余字段保留并再次检查。
原 Analysis 若有错误，需要重新生成，不能通过只改回复文本绕过。

批准请求只提交 context_id、draft_id、expected_lock_version；不提交任意 final_text、
validation_passed、role 或 Evidence。后端加载准确文本，重新运行规则和 Clock 检查。
Context 存储的 freshness 是创建时结论；批准时必须按原时间戳重算，不能永久冻结 FRESH。
如果时效改变而回复不再满足限定语/质量披露，批准失败；允许编辑或手动重新取数。
使用中的 policy_version 必须与 Context 一致；规则配置改变需新 Context，否则 409 POLICY_CHANGED。

Validation PASS 只表示确定性检查通过，不能替代人工阅读。批准表示审核人已看过最终
文本及质量信息；高风险请求只能转人工流程，永远不能执行或声称已执行。

## 6. 可验收例子

| 例子 | 版本链 / 结果 |
| --- | --- |
| 正常 | run 1 → Context 1 → draft revision 1 → PASS → Approval 绑定三者，APPROVED |
| 新取数失败 | 原 Context 1 / draft 1 清为历史；run 2 FAILED；OPEN；批准 draft 1 返回 409 |
| 编辑后重验 | draft 1 PASS；编辑 revision 2 为“保证今天送达”；FAIL；批准 2 返回 422；1 也不能批准 |
| 新版本淘汰旧版 | run 2 成功 → Context 2；旧 draft.context_id = Context 1，生成/批准旧版本返回 409 |
| 重复点击 | 两个相同 key/request 的批准只产生一条 Approval；不同文本或版本的重放返回 409 |
| 部分失败 | 两包裹中一个 timeout；run PARTIAL；Context DEGRADED；只允许披露局部已知与失败 |
| 放置过久 | 生成时 FRESH，批准时取数超过 30 分钟；重算 STALE，未经限定的现状声明被拒绝 |

拒绝、失败与成功都写安全 Audit；校验结果包含稳定 code 和字段位置，不记录 token、
原始 HTTP body 或问题/回复全文到普通日志。测试入口见 [验收矩阵](core-mvp-acceptance.md)。
