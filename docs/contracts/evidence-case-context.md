# Evidence / CaseContext 与数据质量契约

契约版本：`core-mvp-v1`。输入仅为 [canonical v1](../external-system-contract.md) 的
现有 Provider 结果；本阶段不实现 resolver、缓存、重试或 Evidence Engine。
取数/版本门见 [生命周期](core-lifecycle.md)，数据记录见 [core-data](core-data.md)。

## 1. 来源结果与编排

SourceFetch.operation 固定为 `get_inquiry | get_order | get_parcels | get_shipment | get_notes`。
get_shipment 指既有 LogisticsProvider 对一个 parcel 的完整操作（shipment + events）；
第二个 HTTP 请求失败时整体失败，不能宣称已拿到完整 ShipmentSnapshot。
按 Inquiry → order → parcels → 各 parcel shipment / notes 的依赖编排；无权时零调用。
成功读取的 Inquiry ID 与订单引用须与 Product 绑定一致，不一致立即失败。

| outcome | canonical_payload / fetched_at | 业务含义 |
| --- | --- | --- |
| SUCCESS | `{records: [...]}` 非空 / 成功调用时间 | 此操作取得有效 canonical 记录，仍须判断时效 |
| EMPTY | `{records: []}` / 成功调用时间 | 数组操作成功但无记录；不等于尚未发货等结论 |
| NOT_FOUND | null / null | ExternalNotFound；来源未返回目标记录 |
| NO_TRACKING | null / null | parcel.tracking_number = null；不调用 LogisticsProvider |
| TIMEOUT | null / null | ExternalTimeout；不知道该来源当前业务状态 |
| UNAVAILABLE | null / null | ExternalUnavailable，包括 429/5xx/传输失败 |
| INVALID_RESPONSE | null / null | ExternalInvalidResponse，不能使用其中任何未经验证字段 |
| REJECTED | null / null | ExternalRejected；记录安全错误分类 |
| CONFLICT | null / null | ExternalConflict；来源请求冲突，不等于业务事实冲突 |

SourceFetch 永远有 completed_at；NO_TRACKING.error_code = NO_TRACKING，其他失败用上表
同名安全 code。SUCCESS/EMPTY.error_code = null。未执行的依赖操作不伪造 SourceFetch；
FAILED run 用 error_code 指出停止原因；没有 Context 不代表成功空结果。
Context 的 source_outcomes 包含每次已执行操作及每个已知 parcel 的 NO_TRACKING 结果。
get_inquiry/get_order/get_parcels 的失败阻止 Context；其余失败为 PARTIAL，规则见生命周期。

## 2. Evidence 形状与引用

一个 Evidence 只对应一处 canonical 值，不能拼接两个来源伪造一个事实。

| 字段 | 类型 / 规则 |
| --- | --- |
| id | `ev-` + SHA-256(snapshot_id + 换行 + pointer)；64 位小写 hex，不截断 |
| kind | FACT（结构化字段）或 SOURCE_TEXT（备注、事件描述等自由文本） |
| source_system、source_record_id | 从所定位记录继承；事件必须使用实际 event ID |
| snapshot_id、snapshot_version | 成功 SourceFetch.id 与所属 Run.version；不可变 |
| pointer | JSON Pointer，如 `/records/0/status` 或 `/records/0/events/0/status` |
| value | pointer 所定位的原始 JSON 值；类型和值均严格相等 |
| source_updated_at | 必需 nullable；该记录自己的源时间，事件不得继承 shipment 的更新时间 |
| fetched_at | 该 canonical 记录原始 Product 时间；不因 Context 读取而更新 |
| occurred_at | 必需 nullable；事件用自己的发生时间，其余 null；不是 freshness 的替代值 |
| freshness_status | 创建 Context 时按下述规则计算的 FRESH / STALE / UNKNOWN |

快照 envelope 为 `{records: [canonical...]}`，get_order/get_inquiry/get_shipment 是单元素数组。
数组保持 Provider 顺序，引用以不可变 snapshot + pointer 定位，不按“第一条就是最新”推断。
Evidence 引用必须在同一 Context，并可回溯到同一 Inquiry 的 run/snapshot。
FACT 允许结构化 status、tracking_number、order items 等；SOURCE_TEXT 可证明“来源记录写了
这些字”，不能证明其中承诺、权限或行动已发生。空查询由 source_outcomes 证明，不造
“未发货” Evidence。注入式文字原样保留为不可信数据，不能进入规则/工具指令。

## 3. 可配置时效规则

组合 policy_version = `core-policy-v1`，同时绑定 `freshness-v1` 与 `validation-v1`。
freshness_policy.version = `freshness-v1`；配置值快照随 Context 保存，批准时按同一版本重算。
配置必须为正整数秒；配置变化形成新版本，旧 Context 不能混用新配置。

| 记录类别 | source_max_age_seconds | fetch_max_age_seconds |
| --- | --- | --- |
| order、parcel metadata、warehouse note | 86400（24 小时） | 1800（30 分钟） |
| shipment、shipment event | 21600（6 小时） | 1800（30 分钟） |

在评估时间 t（Clock）按顺序判定：

1. fetched_at > t 或非 null 的 source_updated_at > t → UNKNOWN，flag = CLOCK_ANOMALY。
2. source_updated_at = null → UNKNOWN；记录 fetch_age，但不能因新 fetch 变为 FRESH。
3. 否则 source_age > source_max_age 或 fetch_age > fetch_max_age → STALE。
4. 否则 FRESH。恰好等于阈值仍 FRESH，超出一微秒即 STALE；source_age/fetch_age 不取整。

UNKNOWN 也可能有 fetch_age 超限，须额外标明 OLD_FETCH；不能隐藏取数过旧。
occurred_at 不替代 source_updated_at；新 fetch 到 72 小时旧物流仍为 STALE。
新生成/批准时根据原时间重评质量与披露要求，不修改历史 Context 中已存的判定。
无缓存 fallback、自动重试或从旧 run 补洞。本规则是 MVP 演示默认值，非承运商时效承诺。

## 4. 状态、缺失与冲突

raw status 保留原字符串。shipment 已知值为 LABEL_CREATED、NOT_COLLECTED、PICKED_UP、
IN_TRANSIT、DELIVERED、EXCEPTION；order 已知值为 PAID、WAITING_STOCK、PACKED、SHIPPED、
PARTIALLY_SHIPPED、PROCESSING、DELIVERED。未知值不变成 DELIVERED 或“正常”。
shipment.status = null 也产生 UNKNOWN_STATUS；保留 null Evidence，不在 Analysis.current_status
中编造字符串或最新业务结论。所有列出的已知值仅是解释词表，不改变 Provider 的开放字符串类型。
当前状态取 shipment.status，事件只表示当时发生的记录；不同时间的 LABEL_CREATED 与
IN_TRANSIT 是正常历史，不能仅因值不同判冲突。不能用一个包裹代替整个订单。

missing_information 条目为 `{code, scope, evidence_ids}`，scope 为 external_order_id 或 parcel_id。
固定 code：NO_PARCELS、NO_EVENTS、NO_WAREHOUSE_NOTES、NO_TRACKING、SOURCE_NOT_FOUND、
SOURCE_TIMEOUT、SOURCE_UNAVAILABLE、SOURCE_INVALID_RESPONSE、SOURCE_REJECTED、SOURCE_CONFLICT。
evidence_ids 可为空（失败无 Evidence）；必须有对应 source_outcomes 或有效快照支持。
unknowns 为 `{code, evidence_ids}`，code = UNKNOWN_SOURCE_TIME / UNKNOWN_STATUS /
CLOCK_ANOMALY / OLD_FETCH。对于 parcel metadata 时间未知，不能推断 shipment 也未知；
分别评估，整体质量需披露这些字段限制。

conflicts 为 `{id, code, evidence_ids, explanation}`，至少两个不同 Evidence，不能消去任一方。
v1 仅确定两个保守规则：

- 同 parcel、同 occurred_at 的结构化事件 status 不同 → INCOMPATIBLE_EVENT_STATUS。
- 备注原文忽略大小写包含 `not handed to carrier today`、`not been handed to carrier today`、
  `not handed to the carrier today` 或 `not been handed to the carrier today`，
  且同订单有 PICKED_UP / IN_TRANSIT / DELIVERED 的物流状态，备注 created_at 与物流
  source_updated_at 的 UTC 日期相同 → POSSIBLE_HANDOVER_CONFLICT。
  这是 S11 的“可能冲突”提示，不证明哪个来源错；源时间未知时不套用该日期规则。

其他自由文本冲突留给 AI 提出带引用的可能冲突与人工判断；规则并不理解任意语言。
AI 新提出的冲突不能修改程序的 conflicts，须保存在 Analysis 并经人工审核。
仓库计划只保留 source_texts；plans_or_expectations 是 AI 提取，永不混入 facts。

## 5. CaseContext 封闭形状

| 字段 | 内容 |
| --- | --- |
| schema_version | core-mvp-v1 |
| context_id、inquiry_id、run_id、context_version、created_at | 精确版本身份；version = Run.version |
| policy_version、freshness_policy | core-policy-v1；对象含 version = freshness-v1、fetch_max_age_seconds = 1800、source_max_age_seconds（键 order / parcel / warehouse_note / shipment / shipment_event，值为上表秒数） |
| authorization_scope | inquiry_id、external_order_id、team_id、assigned_agent_id；由 Product 绑定生成 |
| question | text、source_system、source_record_id、created_at；来自已验证 SupportInquiry |
| order | external_order_id、status_evidence_id |
| parcels | 每项 parcel_id、tracking_number_evidence_id（nullable）、shipment_status_evidence_id（nullable）、event_evidence_ids |
| source_outcomes | 每项 fetch_id、operation、target_id、outcome、error_code（nullable）、fetched_at（nullable） |
| evidence | 上文完整 Evidence 数组 |
| facts、source_texts | 分别为 FACT / SOURCE_TEXT 的 Evidence ID 数组；无交叉，覆盖所有 Evidence |
| unknowns、missing_information、conflicts | 程序计算的质量信息，按 code/scope/id 稳定排序 |
| quality、risk_flags | COMPLETE / DEGRADED；risk_flags 是下面固定 code 的去重排序数组 |

risk_flags = STALE_DATA / UNKNOWN_FRESHNESS / PARTIAL_SOURCE_FAILURE / MISSING_INFORMATION /
CONFLICTING_SOURCES / UNKNOWN_STATUS / CLOCK_ANOMALY。只在相应情况存在时加入。
全部必需操作成功、无部分失败/缺失/冲突、所有 Evidence FRESH 且 status 可识别才 COMPLETE；
其余可用 Context 为 DEGRADED。真实 S02 的 parcel/event 更新时间 null，因此也是 DEGRADED；
不能为了“正常场景”省略此限制。所有 Context 都需人工审核，COMPLETE 不代表自动批准。

AI 只接收上述已授权 Context；不传 token、密码哈希、无关客户、外部 URL/数据库连接、
可执行工具、其他 Inquiry 或全部历史快照。scope 是限制说明，不是模型可修改的权限凭据。
安全披露内容从程序 quality 导出；AI 不能删掉质量 flags 来获得批准。

## 6. 完整示例与测试

[examples/core-contexts.json](examples/core-contexts.json) 包含 NORMAL、MULTI_PARCEL、STALE、
SOURCE_FAILURE、UNKNOWN_TIME、CONFLICT 六个完整 Context，以及每个引用对应的 canonical
快照 envelope。例子是 **Product fixture**，不是六次真实 Sandbox 抓取结果；只覆盖必要字段，
真实 Sandbox 场景依据 [验收矩阵](core-mvp-acceptance.md)重新通过 HTTP 读取。
示例用真实格式 UUID、固定 Clock `2026-09-20T06:00:00Z`，可以机械验证每个 pointer、
Evidence ID、源时间、quality 与关联；失败项没有伪造快照。

同一快照集合、版本、配置与 Clock 生成完全相同的 Evidence 和质量信息。Snapshot/Context ID
先由取数记录分配；此“确定性”不要求两次不同 run 复用 UUID。覆盖阈值相等/超界、未来时间、
null、旧 fetch、事件更新时间隔离、空数组、部分失败和跨 Context 引用的测试是 Stage 4 出口。
