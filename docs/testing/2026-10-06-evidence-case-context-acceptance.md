# Evidence / CaseContext 数据验收标准

日期：2026-10-06；契约 `core-mvp-v1`、组合规则 `core-policy-v1`。
本文件是 Stage 4 交接检查表，不是已实现/已通过声明，不替代
[Evidence](../contracts/evidence-case-context.md)、[API](../contracts/core-api.md)、
[数据](../contracts/core-data.md)与[生命周期](../contracts/core-lifecycle.md)契约。
输入覆盖见 [场景清单](2026-10-06-stage-4-scenario-coverage.md)。

## 1. 开始实现前的依赖

- main 已含契约、数据库 0001/0002 和 Stage 3 auth/Inquiry API。
- 当前 `/order` 只返回无绑定 422 或缺 Context 409。不要提前改成无版本实时取数。
- 应用侧定义 Context/Evidence 的闭合可执行 schema，复用 canonical Provider 类型，
  不直接连接 Sandbox SQLite，也不绕过 Provider 读取 fixtures。
- 先明确 RUNNING 的开始/结束短事务、授权重查、幂等、失败提交及中断恢复，再接网络。

## 2. 质量检查表（全部待 Stage 4 实现验证）

| 维度 | 必须通过的验收标准 |
| --- | --- |
| 授权范围 | 身份 → Inquiry 权限 → 状态/输入 → 取数；返回后/提交前重查身份与归属。所有引用同 Inquiry/run，order 来自 Product 固定绑定；无权零来源/模型调用 |
| 来源完整性 | inquiry/order/parcels 是必需来源；失败无 Context。枚举成功后逐包裹完整记录物流与 notes 的 outcome，不丢掉失败包裹 |
| 成功与失败 | SUCCESS 为非空 records，EMPTY 仅数组 records=[]；两者 payload/fetched_at 非 null、error_code null。其他 outcome/NO_TRACKING payload/fetched_at null，completed_at 保留，不能以完成时间冒充成功抓取时间 |
| 时间保真 | source_updated_at required nullable；fetched_at 保留适配器原值；事件使用自己的 source/occurred 时间，不能继承 shipment 更新。SupportInquiry 不凭空增造 canonical fetched_at |
| 引用可追溯 | ID = ev- + SHA256(snapshot_id + 换行 + pointer)，64 位小写 hex；pointer 定位不可变 records envelope；value 类型和值完全一致；源记录 ID/版本与该位置一致 |
| 信息类别 | facts 与 source_texts 无交叉、覆盖全部 Evidence；计划/备注只证明来源写了什么，不能证明已执行；注入文字不能获得权限/工具 |
| 范围与状态 | 一订单多个 parcel 独立关联，raw status 保留；未知/null shipment 状态标 UNKNOWN_STATUS，不变“正常/已送达”。不能因事件数组首项推断当前状态 |
| 缺失/冲突 | missing 有 outcome/快照支持；失败无 Evidence 不造引用。同 parcel 同时间不同事件状态标冲突；S11 仅匹配契约四种英文短语与同 UTC 日期规则，保留双方引用，不能裁决正确来源 |
| 整体质量 | SUCCEEDED 是取数成功，不等于 COMPLETE。COMPLETE 需全来源成功、无缺失/冲突、所有 Evidence FRESH 且状态已知；否则可用 Context DEGRADED。真实 S02 也是 DEGRADED |
| 安全 | Context 不含 token/hash/URL/连接串/无关客户；schema 拒绝额外字段；普通日志/Audit 不复制问题、源 payload 或回复全文；无发送/退款等动作 |
| 确定性 | 相同已分配 snapshot IDs、版本、配置、Clock 得同 Evidence/质量结果；新 run 不要求复用 UUID；quality 条目/flags 稳定排序去重 |
| 历史 | SourceFetch/Context 追加不可变；新 resolve 开始即旧当前指针失效；失败保留历史但不恢复为当前；历史读取仍鉴权 |

## 3. Freshness 边界

固定 `freshness-v1` 配置随 Context 保存：fetch 1800 秒；
order/parcel/warehouse_note 源年龄 86400 秒；shipment/shipment_event 21600 秒。

按优先级参数化验证：

1. fetch 或非 null source 在未来：UNKNOWN + CLOCK_ANOMALY。
2. source=null：UNKNOWN；即使刚 fetch 也不是 FRESH；fetch 超龄另加 OLD_FETCH。
3. source 或 fetch age 大于其阈值：STALE。
4. 其余 FRESH；恰等阈值 FRESH，超一微秒 STALE，不能取整。

发生时间/created_at 不替代源时间。UNKNOWN_FRESHNESS、STALE_DATA 等 risk_flags
由程序导出；新 fetch 不刷新旧源事实。后续 Stage 5 批准时重评原时间，
不得修改历史 Context 的判定或永久沿用曾经 FRESH 的结果。

## 4. 状态、幂等和事务出口

- 开始 resolve 短事务：授权、幂等重放/冲突检查、再检查新操作的状态/版本，写 RUNNING，占用 Inquiry，
  清当前 Context/Draft、递增 lock_version，再结束事务执行 HTTP。
- 结束短事务：重查当前授权/占用与关联，保存 SourceFetch、不可变 Context/安全 Audit，
  写 SUCCEEDED/PARTIAL/FAILED 并释放占用，再递增 lock_version。
- FAILED 为 OPEN、无新 Context；局部失败/NO_TRACKING 为 PARTIAL + DEGRADED；
  全部成功（包括 EMPTY）为 SUCCEEDED，质量可 DEGRADED。
- 同 key 同请求先鉴权再重放，检查先于 expected_lock_version；RUNNING 返回 202；
  同 key 不同请求 409。已有成功/失败均不重新调用，无自动重试或旧 run 补洞。
- 两个真实 PostgreSQL 事务验证忙碌/换权/版本竞争；FK 存在不替代跨行关联验收。
- 意外数据库错误回滚；有意保存的 FAILED run 与拒绝请求必须明确区分。
  不直接把 resolver 加入 Stage 3 捕获 ApiError 后提交 Audit 的通用包装器。
- 提供针对目标 RUNNING 操作的人工恢复 runbook 和测试；不批量清库、不自动恢复取数。

## 5. 浏览器与 API 出口

Stage 4 提供 resolve/run/context 和有效当前 Context 的 order 读取；封闭字段、
授权历史资源、缺失与错误映射沿冻结 API，不开放任意外部 order_id 搜索。
trusted Origin 的 `Idempotency-Key` preflight 必须有测试；当前 CORS 尚未允许该 header。
Stage 5 的 PATCH method 另行扩展，不在 Stage 4 夹带草稿编辑/模型调用。

## 6. 数据负责人签收条件与留痕

只有以下完成才签收 Stage 4 数据质量，不能以页面能打开或模型能回复代替：

- [ ] 场景矩阵所列 Stage 4 正反例有可运行测试与逐项证据，未执行项明确保留。
- [ ] 来源映射/故障经过独立 Sandbox HTTP；规则补充用标明来源的 Fake Provider/Clock。
- [ ] PostgreSQL 证明版本链、幂等、并发、回滚、权限重查和不可变历史。
- [ ] Evidence ID/pointer/value/type/时间/归属机械校验，无丢包裹/伪造事实。
- [ ] 质量标记和 freshness 边界全部验证；失败、EMPTY、UNKNOWN、CONFLICT 分开。
- [ ] runbook、安全日志、API/CORS 与 runtime 无 LLM/发送行为有测试。
- [ ] PR、基线 SHA、规则版本、Clock、passed/failed/skipped 与修复记录可追溯。

发现缺陷必须先登记：问题 ID、场景、预期/实际、根因、影响文件、修复提交、
回归测试和复验结果。没有行为缺陷不为了留痕制造修改；不把 AI 审查冒称两名开发者批准。
AI 接入仅准备评估结构；Stage 4 数据出口通过后另行启动 Stage 5。
