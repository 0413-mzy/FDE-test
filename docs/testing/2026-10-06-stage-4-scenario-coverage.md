# Stage 4 场景覆盖与缺口交接

日期：2026-10-06。数据/测试负责人交付；应用负责人实现 resolver/Evidence。
基线：main `8469971982a82369c94ab9387ab73d55f6caf6a6`。
依据：[冻结验收矩阵](../contracts/core-mvp-acceptance.md)、
[Evidence 契约](../contracts/evidence-case-context.md)、
[生命周期](../contracts/core-lifecycle.md)。本文件不更改契约，也不是 Stage 4 通过报告。

## 1. 目前究竟覆盖了什么

`backend/tests/integration/test_sandbox.py` 已有 13 项真实 HTTP 测试，验证单个
Provider 的映射、错误和消息边界，不验证 resolver、Evidence、Context 或 AI。
本轮只检查其源码，未重跑独立 Sandbox。六个完整 Context JSON 是 Product fixture，
不是六次真实抓取。Stage 4 行为和所有下表的 resolver 断言均待实现、待运行。

## 2. 可复用真实 Sandbox 来源

统一 Clock：`2026-09-20T06:00:00Z`。未来运行固定 Product/Sandbox SHA，
仅使用独立临时 Sandbox，通过 HTTP 访问，不 reset 共享服务、不读取其 SQLite。

| CORE 场景 / 来源 | 已有 Provider 测试证明的范围 | Stage 4 必须新增的断言 |
| --- | --- | --- |
| CORE-01 / S02 | 订单 SHIPPED、物流 IN_TRANSIT、原始源时间；event 更新 null | run SUCCEEDED；Context DEGRADED，不能把正常场景硬标 COMPLETE；每项 Evidence 可定位 |
| CORE-02 / S04 | 两包裹分别 IN_TRANSIT / NOT_COLLECTED；parcel 更新时间 null | 两包裹均在 Context，scope 分开；不做“全部已发货”结论 |
| CORE-03 / S06 | 备注原样保留预计发货措辞；物流 NOT_COLLECTED | 备注仅 SOURCE_TEXT；不可转为已发货 FACT；AI 的 PLAN_AS_FACT 拦截属于 Stage 5 |
| CORE-04 / S07 | shipment 源时间 T0−72h；新 fetched_at 为 T0 | STALE_DATA；源时间不覆盖、不能因新 fetch 标 FRESH |
| CORE-05 / S08 | 真实 HTTP 504 映射 ExternalTimeout；其他来源可读 | TIMEOUT outcome 无 payload/fetched_at；run PARTIAL，保留成功部分，不造 EXCEPTION |
| CORE-06 / S09 | 仓库 503；物流仍可读 | UNAVAILABLE，不改成 EMPTY；Context DEGRADED、明确仓库缺口 |
| CORE-07 / S10 | OMS 有一个 parcel，物流 404 | NOT_FOUND，不是无包裹；保留 OMS parcel 与 SOURCE_NOT_FOUND |
| CORE-08 / S11 | 两来源原文及 PICKED_UP 均保留 | 按同 UTC 日期规则标 POSSIBLE_HANDOVER_CONFLICT；至少双 Evidence，不裁决哪方正确 |
| CORE-09 / S12 | Inquiry 存在、绑定订单 404 | run FAILED、OPEN、无新 Context；404 SOURCE_NOT_FOUND；无 LLM 调用 |
| CORE-10 / S01 | parcels 200 + [] | EMPTY、NO_PARCELS；成功传输不等于已发货或超时 |
| CORE-11 / S05 | note 更新时间 null；fetch 为 T0 | UNKNOWN_SOURCE_TIME / UNKNOWN_FRESHNESS；不借 created_at/fetch 补源更新时间 |

S08 是即时 HTTP 504，不是 socket 超时；S10 是物流 404，不是成功空数组。
S05 空包裹是外部契约列出的能力，但现有 S05 测试只断言备注时间；
Stage 4 若使用它的空包裹路径，需要新增真实 HTTP 断言。

## 3. 必须补充的 Product 测试

下列不声称由 S0–S1 seed 覆盖；用符合 canonical 协议的 Fake Provider、
FixedClock、隔离 PostgreSQL 补充。adapter 的 mock transport 测试不能代替 resolver 测试。

| ID / 输入 | 必须证明的结果 |
| --- | --- |
| CORE-12–14 / 五身份与越权 | 无 session、过期、撤销、停用 401；无权/未知 Inquiry 403 同形；Provider/LLM 零调用；同 team Supervisor 合法 |
| CORE-15–16 / 伪造绑定、无订单绑定 | 额外 role/team/order 字段拒绝；来源 ID/订单绑定不一致 FAILED；无绑定 422，零订单调用、不猜订单 |
| CORE-17 / 两包裹、一失败 | 正常包裹保留，失败包裹有独立 outcome；不得丢弃失败 parcel 或伪造物流字段 |
| CORE-17 / tracking=null | NO_TRACKING、零 LogisticsProvider 调用；run PARTIAL、Context DEGRADED |
| CORE-18 / 未知 status、未来 source/fetch | raw status 保留；UNKNOWN_STATUS / CLOCK_ANOMALY；不变 DELIVERED |
| CORE-19 / 阈值及 null+旧 fetch | 精确等于阈值 FRESH，超一微秒 STALE；null 为 UNKNOWN，旧 fetch 加 OLD_FETCH；不取整 |
| CORE-20 / 恶意仓库自由文本 | 原文 SOURCE_TEXT；无新增权限/动作；不把文字当事实或程序指令；回复拦截留 Stage 5 |
| CORE-24 / 成功后新 resolve 成功或失败 | 开始即清空旧当前指针，失败不恢复；历史保留，新 run 递增版本；无旧草稿批准资格 |
| CORE-26 / resolve 幂等、并发与换权 | 同 key 同请求不重复取数，RUNNING 重放 202；不同 body 409；忙碌/旧版本拒绝；网络返回后重新检查当前身份归属 |
| CORE-30 / 调用中断 | 保留 RUNNING/BUSY，不自动覆盖或重调用；人工 runbook 仅对目标操作写 FAILED/Audit 并释放占用 |
| 补充 / events 子请求失败 | get_shipment 整体失败；不能存半个成功 ShipmentSnapshot |
| 补充 / 429、socket timeout、坏 JSON、重复 ID、绑定错 | 对应安全 outcome；必需来源失败无 Context，局部失败保留成功部分；无未经验证字段入库 |
| 补充 / 跨 Inquiry snapshot/Context 与历史读取 | 拒绝关联越界；历史每次重新授权，不能把外键有效当作链有效 |
| 补充 / 浏览器 preflight | trusted Origin + Idempotency-Key 通过；未知 Origin 先拒绝、零 DB/Provider 调用 |

## 4. 两人交接与出口

数据/测试侧交付本矩阵、[质量验收标准](2026-10-06-evidence-case-context-acceptance.md)
及 canonical 正反样本；应用侧实现闭合 schema、来源编排、事务/版本/API 与确定性规则。
新增样本先标来源与预期，不扩展 Sandbox，不复制完整订单库。

每项 Stage 4 场景必须记录：输入 fixture/来源 SHA、Clock、规则版本、API status/code、
run 状态、SourceFetch outcome、Context 质量、Evidence 引用、调用计数及安全版本链。
只有实际运行的场景写 passed；源级通过、文档样例可解析与 resolver 通过分别记录。
Stage 5/6 的生成、批准和 UI 断言不计入本轮 Stage 4 通过数。
