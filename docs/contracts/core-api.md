# Core MVP 身份、授权与 API 契约

契约版本：`core-mvp-v1`；Stage 3 已实现 auth/Inquiry 读取及 order 前置条件入口，
2026-10-06 用户授权自审后合并 PR #5。详见 [实现边界](stage-3-implementation.md)。
表中 Stage 4/5 路由仍是后续设计，未实现；order 的 200 快照读取仍属于 Stage 4。
状态/幂等顺序见 [生命周期](core-lifecycle.md)，实体见 [数据契约](core-data.md)。

## 1. 最小会话

用户名/密码登录使用 Argon2id 密码哈希和库管理的随机盐；不存明文/可逆密码。
v1 哈希参数固定为 memory_cost = 65536 KiB、time_cost = 3、parallelism = 1，
salt 至少 16 字节、hash 至少 32 字节。Seed 密码长度 12–128，缺失/不合格即失败；
登录 username 为 3–64 个 ASCII 字母/数字/`._-`，password 为 1–128 个字符，不能 trim。
未知用户名、密码错、停用账号统一 401 AUTHENTICATION_FAILED；响应不披露账号是否存在。
测试密码只从显式测试环境配置读取，普通日志与 fixtures 不放真实凭据。

登录生成至少 32 个密码学随机字节的不透明 token，base64url 编码；服务端只存其 SHA-256
摘要和 AuthSession。有效期固定 8 小时，从创建起不滑动；无 refresh token。
后续请求 `Authorization: Bearer <token>`；每次核验过期/撤销、User.is_active、当前 role/team。
`now >= expires_at` 即 401；退出撤销当前 session。前端 token 只存内存，刷新后重新登录，
不写 URL、localStorage 或普通日志。部署使用 HTTPS，开发 origin 显式列入 CORS，不能用 `*`。
不用认证 cookie，不引入 cookie/CSRF 流程；browser 不能从未知 origin 获得认证响应。
登录不回显 password_hash、token_digest；会话响应加 `Cache-Control: no-store`。
后续部署还需专门评审登录防暴力破解与运行配置；本阶段不实现限流/重试系统。

## 2. 权限矩阵与顺序

| 角色 | list / detail / order / context | resolve / generate / edit / approve / escalate |
| --- | --- | --- |
| AGENT | Inquiry.assigned_agent_id = 当前 User 且 team 相同 | 同左；再满足状态/版本条件 |
| SUPERVISOR | Inquiry.team_id = 当前 User.team_id | 同左；不能越过 Validation 或执行高风险动作 |
| ADMIN | 无业务权限，list 返回空 | 403 FORBIDDEN；系统管理不包含业务读权 |

每个入口：认证 → 身份当前有效 → Inquiry 授权（包括关联资源归属）→ 状态/版本/输入 →
Provider 或存储读取 → 再校验关联 → 返回最小结果。异步调用结束、写入/批准提交前重新检查
当前授权；外部事实、用户输入的 order_id/role/team、AI 输出不能形成新权限。
订单只通过已授权 Inquiry 的绑定读取，无 `/orders/{任意外部ID}` 搜索、换绑或开放详情入口。

未知或无权的格式合法 Inquiry UUID 统一 **403 FORBIDDEN**，内容完全相同；不披露存在性、
assignee、team 或订单号。权限拒绝先于 Provider/LLM，调用次数必须为零。
关联资源在已授权 Inquiry 下不存在 → 404 RESOURCE_NOT_FOUND；已知其他 Inquiry 的
Context/draft/run ID 同样用这个 404，不披露归属。格式错误 → 422 INVALID_REQUEST。
先认证再报告请求错误，防止未登录者读取 schema/资源差异。

## 3. 入口表

请求/响应均 JSON，封闭字段、禁止额外字段；内部 ID 为 UUID，时间 UTC `Z`。
`X-Request-Id` 接受非空 1–100 字符的字母/数字/`._-`，否则生成 UUID；回显于 header 与错误体。
列表固定按 created_at DESC、id DESC，limit 默认 20 / 最大 100，offset 默认 0。
所有业务响应 `Cache-Control: no-store`；不实现业务缓存。

| 方法与路径 | 输入 | 成功响应 / 状态 | 实现 Stage |
| --- | --- | --- | --- |
| POST /api/v1/auth/login | username、password；不需要已有 session | 200：token、token_type = Bearer、expires_at、user | 3 |
| GET /api/v1/auth/me | bearer | 200：id、username、role、team_id | 3 |
| POST /api/v1/auth/logout | bearer，无 body | 204；撤销当前 session | 3 |
| GET /api/v1/inquiries | limit、offset | 200：items（授权范围的摘要）、limit、offset、total | 3 |
| GET /api/v1/inquiries/{id} | 无 body | 200：InquiryView | 3 |
| GET /api/v1/inquiries/{id}/order | 无 body；不接受 order_id | 200：最新当前 Context 的 order 快照及其 freshness / Context ID；不取新数据 | 4；Stage 3 缺 Context 返回 409 |
| POST /api/v1/inquiries/{id}/resolve-context | expected_lock_version；Idempotency-Key | 201：run_id、state、context_id、context_version、quality、lock_version | 4 |
| GET /api/v1/inquiries/{id}/runs/{run_id} | 无 body | 200：id、state、version、context_id?、error_code?、lock_version | 4 |
| GET /api/v1/inquiries/{id}/contexts/{context_id} | 无 body | 200：完整 CaseContext，附 is_current（外层字段） | 4 |
| POST /api/v1/inquiries/{id}/generate-draft | context_id、expected_lock_version；Idempotency-Key | 201：DraftView；RUNNING 重放为 202 | 5 |
| GET /api/v1/inquiries/{id}/generations/{attempt_id} | 无 body | 200：id、state、draft_id?、error_code?、lock_version | 5 |
| GET /api/v1/inquiries/{id}/drafts/{draft_id} | 无 body | 200：DraftView；历史附 is_current = false | 5 |
| PATCH /api/v1/inquiries/{id}/draft | expected_draft_id、expected_lock_version、reply_text | 201：新 DraftView；不修改原 revision | 5 |
| POST /api/v1/inquiries/{id}/approve | context_id、draft_id、expected_lock_version；Idempotency-Key | 201：ApprovalView；同 key 重放为 200 | 5 |
| POST /api/v1/inquiries/{id}/escalate | expected_lock_version、reason（1–1000 非空字符） | 200：InquiryView，state = ESCALATED | 5 |

InquiryView：id、external_inquiry_id、external_order_id（nullable）、state、lock_version、
current_context_id、current_draft_id、latest_run_id（三者 nullable）、created_at、updated_at。
详情另含 escalation_reason（required nullable，只有 ESCALATED 非 null）；列表摘要不含该原文。
问题原文从授权 Context.question 读取；未取数时不假造 question 或来源时间。
DraftView：id、revision、context_id、analysis、reply_text、text_hash、validation
（status、errors、warnings、evaluated_at、policy_version、validator_version）、is_current、lock_version。
ApprovalView：id、inquiry_id、context_id、draft_id、reviewer_id、text_hash、approved_at、state = APPROVED。
不包含 sent_at、reply_receipt 或任何执行承诺。回复 1–10000 字符，保留原文本；非空白。

没有 Product send/refund/cancel/address/payment/compensation 路由，也没有自动发送状态。
当前 SandboxMessageProvider.send_reply 的存在不授权该 API 在 MVP 使用它。

## 4. 请求/响应例子

以下 ID 使用真实格式的虚构 UUID；没有密码或会话 token 样例值。
resolve 请求 header `Idempotency-Key: resolve-demo-002-1`：

```json
{"expected_lock_version": 1}
```

成功响应（字段 version 与 run 相同，lock_version 以服务端实际值为准）：

```json
{
  "run_id": "20000000-0000-4000-8000-000000000002",
  "state": "SUCCEEDED",
  "context_id": "30000000-0000-4000-8000-000000000002",
  "context_version": 1,
  "quality": "DEGRADED",
  "lock_version": 3
}
```

该例传输完全成功，但真实 S02 的 parcel/event 更新时间 null，所以整体质量不是 COMPLETE。
generate 请求：

```json
{"context_id":"30000000-0000-4000-8000-000000000002","expected_lock_version":3}
```

edit 请求：

```json
{"expected_draft_id":"40000000-0000-4000-8000-000000000002","expected_lock_version":5,"reply_text":"根据 2026-09-20 05:50 UTC 的物流记录，包裹当时在运输中；部分来源未提供更新时间，暂无法保证送达日期。"}
```

approve 请求使用新的 revision ID 与最新 lock_version：

```json
{"context_id":"30000000-0000-4000-8000-000000000002","draft_id":"40000000-0000-4000-8000-000000000022","expected_lock_version":6}
```

无权响应（未知 Inquiry 同形，不回显任何订单事实）：

```json
{"error":{"code":"FORBIDDEN","message":"无权访问此咨询。","request_id":"req-demo-denied","details":{}}}
```

## 5. 错误映射

错误 envelope 固定 `{error: {code, message, request_id, details}}`；details 只含安全的
run_id、attempt_id、field_errors、validation_codes 等。禁止原 HTTP body、token、客户内容。

| 状态 | code | 含义 / 后续操作 |
| --- | --- | --- |
| 401 | AUTHENTICATION_FAILED / UNAUTHENTICATED | 凭据错误或 session 缺失/过期/撤销；重新登录 |
| 403 | FORBIDDEN | 不在授权范围，包含未知 Inquiry；不能取事实 |
| 404 | RESOURCE_NOT_FOUND / SOURCE_NOT_FOUND | 授权范围内的历史资源不存在 / 必需外部记录 404 |
| 409 | VERSION_CONFLICT / CONTEXT_REQUIRED / CONTEXT_SUPERSEDED / STATE_CONFLICT / BUSY / IDEMPOTENCY_CONFLICT / POLICY_CHANGED | 查看最新状态、编辑或使用新 key 手动取数；不自动重试 |
| 422 | INVALID_REQUEST / ORDER_REFERENCE_MISSING / VALIDATION_FAILED | 请求/schema/业务校验失败；修正输入或转人工 |
| 502 | SOURCE_INVALID_RESPONSE / SOURCE_BINDING_MISMATCH / SOURCE_REJECTED / GENERATION_FAILED | 必需来源不合法/绑定错，或模型调用/schema 失败 |
| 503 | SOURCE_UNAVAILABLE | 必需来源 5xx/429/传输不可用 |
| 504 | SOURCE_TIMEOUT | 必需来源 504 或超时 |

ExternalConflict 在必需来源上为 409 SOURCE_CONFLICT。所有 External 错误在可选物流/仓库上
记录在 PARTIAL run / DEGRADED Context 内，整体 resolve 仍返回 201；不可混同为全成功。
无订单绑定的 order 读取也返回 422；当前 Context 无效/不存在时为 409 CONTEXT_REQUIRED。
结构化合法但 Validation FAIL 的草稿仍可保存并返回 201，以便编辑；approve 则 422。
事务内部错误返回 500 INTERNAL_ERROR，只给 request_id；不部分提交 Approval。

## 6. 明确拒绝样例

Agent A 访问 B 或 team-2 C 的 Inquiry、Admin 读业务 → 403，Provider/LLM 零调用。
Agent A 把另一个订单 ID、role、validation_passed 加进 resolve/approve body → 422，
即便声明“已获授权”也不使用这些字段。外部 Inquiry.order_id 与既有绑定不同 → 502，不换绑。
无订单 Inquiry → 422，保留 OPEN；未登录 → 401；旧 Context/draft → 409；
引用本 Inquiry 下不存在或其他 Inquiry 的历史资源 → 404。
所有规则都由后端测试验证，不能用 UI 隐藏按钮作为验收证据。
