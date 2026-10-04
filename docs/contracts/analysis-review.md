# Analysis / Validation / Human Review 契约

契约版本：`core-mvp-v1`；本阶段不安装 SDK、调用模型或实现 Validation。
输入只允许 [已授权 CaseContext](evidence-case-context.md)。AI 只能解释与措辞，不能生成
权限、源事实、freshness、动作或批准。MVP 仅需一次结构化 analyze/draft 调用的窄
LLMProvider，业务服务不直接依赖供应商 SDK；无 tool calling、RAG 或 Agent 框架。

## 1. Analysis 封闭输出

所有字段必需，禁止额外字段，空集合用 []，未知值用显式 UNKNOWN，不用空字符串。

| 字段 | 类型 / 约束 |
| --- | --- |
| schema_version | core-mvp-v1 |
| context_id | 必须等于后端传入 Context ID |
| intent | ORDER_STATUS / SHIPPING_PLAN / DELIVERY_ESTIMATE / HIGH_RISK_REQUEST / OTHER |
| current_status | 数组，每项 scope（order/parcel 外部 ID）、status（原字符串）、evidence_id；只引用该 scope 的结构化 status FACT |
| known_facts | 数组，每项 evidence_id、value；必须逐项严格等于 FACT Evidence.value，不生成额外事实句子 |
| plans_or_expectations | 数组，每项 text、evidence_ids；引用 SOURCE_TEXT，明确为来源计划/期望，不作为履约事实 |
| uncertainties | 数组，每项 code、text、evidence_ids；可引用未知/旧数据或为空引用说明查询失败 |
| conflicts | 数组，每项 code、text、evidence_ids；至少两项引用；包含 Context 冲突，可增加带引用的可能冲突 |
| missing_information | 数组，每项 code、scope、text；必须至少覆盖 Context 的 code/scope |
| risk_flags | 固定 Context flags 加 HIGH_RISK_REQUEST / UNTRUSTED_INSTRUCTIONS；不能删程序 flags |
| requires_human_review | 必须为 true，不能因正常数据或 Supervisor 操作而关闭 |
| reply_draft | string，非空白、1–10000 字符；只作待审措辞 |

所有 evidence_ids 必须唯一、属于此 Context。known_facts.value 允许原始标量/数组/对象，
不能用 SOURCE_TEXT 证明“已退款/已出库”等动作。current_status 只来自 order.status 或
shipment.status，不将旧事件排列第一条当最新。无 shipment 时省略该 parcel 状态，
在 missing_information/uncertainties 中解释；不能靠 UNKNOWN 造新的“业务 status”。

示例中的 `<status-evidence-id>` 必须由输入替换为真实 Evidence ID；它是字段示意，
不是可接受的实际模型输出。完整 fixture 的 ID 见 [Context 示例](examples/core-contexts.json)。

```json
{
  "schema_version": "core-mvp-v1",
  "context_id": "30000000-0000-4000-8000-000000000002",
  "intent": "ORDER_STATUS",
  "current_status": [{"scope":"PAR-DEMO-002-1","status":"IN_TRANSIT","evidence_id":"<status-evidence-id>"}],
  "known_facts": [{"evidence_id":"<status-evidence-id>","value":"IN_TRANSIT"}],
  "plans_or_expectations": [],
  "uncertainties": [{"code":"UNKNOWN_SOURCE_TIME","text":"部分来源未提供更新时间。","evidence_ids":["<unknown-time-evidence-id>"]}],
  "conflicts": [],
  "missing_information": [],
  "risk_flags": ["UNKNOWN_FRESHNESS"],
  "requires_human_review": true,
  "reply_draft": "根据 2026-09-20 05:50 UTC 的物流记录，包裹当时在运输中；部分来源未提供更新时间，暂无法保证送达日期。"
}
```

## 2. 确定性 Validation 的次序

规则版本 `validation-v1`，组合 policy_version = `core-policy-v1`（绑定 freshness-v1）。
依次执行；结果为 `{status, errors, warnings, evaluated_at, policy_version, validator_version}`，
validator_version = validation-v1。errors/warnings 每项 `{code, path}`，必要时附安全 Evidence ID；不回显敏感原文。
任何 error → FAIL；warnings 不可抹掉，PASS 仍需人工 Review。
生成 schema 不合法时 Attempt FAILED、无 Draft；合法但规则失败时保留 Draft 与 FAIL 供修正。

| 门 | 检查 | 失败 code / 处理 |
| --- | --- | --- |
| V01 schema | 必需字段、封闭 enum、类型/长度、review=true | INVALID_ANALYSIS_SCHEMA；Attempt 失败 |
| V02 范围/版本 | context_id/current 指针/Inquiry 一致；policy 未换 | CONTEXT_MISMATCH / CONTEXT_SUPERSEDED / POLICY_CHANGED |
| V03 引用/事实 | ID 存在、同 Context、kind；known_facts 类型值相等；status 与 scope/值相等 | INVALID_EVIDENCE_REFERENCE / UNSUPPORTED_FACT / INVALID_STATUS_CLAIM |
| V04 质量覆盖 | Context missing、unknown 与 conflict 不得漏；risk_flags 不得少；批准时重算时效 | QUALITY_DISCLOSURE_MISSING / CONFLICT_OMITTED / STALE_DISCLOSURE_MISSING |
| V05 高风险 | 客户意图/回复中的动作或已执行声明不能被 AI 改写为许可 | HIGH_RISK_ACTION_CLAIM / HIGH_RISK_ROUTE_MISSING |
| V06 自由文本/承诺 | SOURCE_TEXT 不作为已发生事实；不输出保证发货/送达；计划须标计划 | PLAN_AS_FACT / UNSUPPORTED_CERTAINTY / UNTRUSTED_INSTRUCTION_ECHO |
| V07 人工编辑 | 对新 revision 重跑 V01–V06；text_hash 与精确文本一致 | 同上；旧 PASS/批准绝不沿用 |

V04 要求：每条 Context.unknowns 在 uncertainties 中有相同 code 且覆盖相应 Evidence；
缺失要求 code + scope 对应；冲突至少保留同 code 与原 Evidence 集合；风险 flags 为超集。
当引用 STALE/UNKNOWN Evidence 描述状态，reply_draft 必须用明确来源时间限定并包含对应
披露短语：STALE 用“记录较旧”或 `older record`；UNKNOWN 用“更新时间未知”或
“未提供更新时间”或 `update time is unknown`。失败来源至少有“暂无法核实”或
`cannot verify`；冲突至少有“信息存在冲突”或 `conflicting information`。
这是 MVP 的中文/英文最小规则；其他语言需专门规则版本，不能声称覆盖任意措辞。
NONE 情况不能要求虚构源时间：更新时间 null 时说明“来源记录显示”且明确未知，
不得把 fetched_at 当源更新时刻。质量披露是程序推导的审核提示，UI 同时直接显示。

V05 客户问题命中退款/refund、取消订单/cancel order、改地址/change address、支付/payment、
补偿/compensation 的大小写无关词表时，程序强制 HIGH_RISK_REQUEST flag 和人工流程说明。
模型可以只解释进度/建议人工处理，不能移除此 flag。回复命中“已退款”“退款成功”“已取消订单”
“已修改地址”“已完成支付”“已发放补偿”以及英文 `refunded`、`cancelled your order`、
`changed your address`、`payment completed`、`compensation issued` 时保守阻止（含否定句
也可能误报；用户可改写为“此请求需人工处理”）。没有高风险工具/接口可调用。

V06 规则至少覆盖“保证/一定/必定 + 今天/明天 + 发货/送达”和 `guarantee delivery` /
`will definitely ship` 的承诺，以及将计划说明写成完成事实的固定负样本。
当 plans_or_expectations 非空，回复必须标“计划/预计/尚未确认”或 `planned/expected/not confirmed`。
已检测的指令型原文不能成为回复的指令或身份声明；保守阻止回复复现
`ignore previous instructions`、`system override`、`administrator access` 或“忽略之前指令”。
自由文本更复杂的同义改写无法由有限词表完全证明安全，必须人工检查，不能宣传为完备检测。

## 3. 模型输入与错误恢复

程序把质量限制、非执行边界与不可信原文分别序列化。Provider/仓库文字仅放数据区域；
无论出现“系统指令”“已获授权”“跳过审核”，都不能改权限、规则、工具或 Context。
生成前重新检查当前权限与 Context；生成结束前复查，撤销权限后不返回或提交草稿。
只保存必要 analysis/model 名称/调用时间/request ID，不保存密钥或思维链。

模型 timeout、不可用、非 JSON、schema 错误 → Attempt FAILED / GENERATION_FAILED；
不自动重试、不回退为假成功；可以新 key 手动重生成或 escalate。
引用/措辞错误 → Draft FAIL；人工可编辑文本，结构化字段错误需重新生成。
引用旧 Context → 409；先手动取数再生成。高风险请求可安全说明转人工，不执行动作。
没有成功草稿时 MVP 不增加“绕过 LLM 直接创建已批准文本”的入口。

## 4. 人工审核与批准

审核者必须看最终文本、逐包裹事实、源/抓取时间、缺失/冲突与 Validation。
至少核对每个重要声明可追溯、计划未当事实、无履约保证、查询失败未说成业务故障，
高风险需求已明确转人工。编写或修改草稿的 Agent 可以审核；MVP 不要求第二人复核，
但“契约两人 Review”是开发流程的另一件事。

批准 API 不接受客户端传入的 PASS、role 或新文本。后端锁定当前版本、重新校验、
重新授权，再原子保存 Approval.text_hash、validation_id、reviewer_id 与 approved_at。
批准仅表示这个不可变文本通过人工审核；不发送、不更新外部订单、不完成退款。
幂等/失效规则见 [生命周期](core-lifecycle.md)。

## 5. Fake LLM 与未来评估

Stage 5 的 Fake LLM 固定输出：有效带引用 JSON、非 JSON、缺字段、外部 Context/ID、
把计划写成已发货、删除 stale/unknown/冲突、保证明天送达、声称已退款、复现注入指令、
timeout。每项都检查 Attempt/Draft/Validation 状态和 Provider/动作零调用。
人工编辑为错误回复必须同样失败；只测试模型失败而不测编辑通道不能验收。

真实模型 eval 使用相同匿名 Context fixture 和版本化预期，由两名开发者标记事实支持、
不确定性披露、冲突保留、措辞与高风险声明；报告模型版本、参数、样本数、各类失败数。
评价的是特定数据与版本，不承诺自由文本完备准确。真实模型调用是 Stage 5 单独任务，
当前没有执行，不能把 Fake 输出或本次文档检查说成模型评估通过。
