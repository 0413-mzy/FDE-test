# Stage 3 实现切片与接口冻结

日期：2026-10-04。用户明确要求“继续我的下一阶段”，授权 Stage 3 依赖候选。
输入仍为 core-mvp-v1 的 [身份/API](core-api.md)及 [持久化](core-data.md)契约。
PR #2/#3/#4 未合并，不将其称为 main 能力，不代替人工 Review。

## 本次接口

- POST auth/login、GET auth/me、POST auth/logout；固定八小时不透明 Bearer 会话。
- GET inquiries（分页、权限过滤）、GET inquiries/{id}（最小详情）。
- GET inquiries/{id}/order：先认证及 Inquiry 授权；无订单绑定为 422
  ORDER_REFERENCE_MISSING，否则为 409 CONTEXT_REQUIRED。本切片不读取已存 Context JSON
  或调用 Provider；完整只读快照入口在 Stage 4 接入有效当前 Context 后开启。
- 无 create/assign/rebind、resolve、AI、草稿编辑/批准、发送或高风险动作路由。

## 具体边界

Session 工厂只在业务请求需要数据库时惰性创建，不在进程启动或 /health 连接数据库。
所有 Product 时间由注入 Clock 产生。32 随机字节的 base64url token 只在登录成功返回，
数据库只存 SHA-256 摘要。密码沿用 Stage 2 Argon2id 参数；未知账号使用一次等参数的
随机 dummy hash 验证，失败文本/状态相同；不声称运行时间完全等同或已具备防暴破能力。

业务事务锁顺序固定为 User → AuthSession → Inquiry。先以 digest 读 user_id，再锁定
当前 User 和重新读取 AuthSession，检验活跃/过期/撤销；读取用 PostgreSQL FOR SHARE，
logout 独占 Session 锁。读期间阻止身份/咨询归属变更。成功会话创建/退出与最小 Audit
同事务提交；登录失败/权限拒绝也记录安全 Audit。未知/无权 Inquiry 统一 403，不记录
外部 ID、输入内容或目标归属；不存在或无权时 Provider/LLM 调用为零。

受保护入口先核验身份，再进行 UUID、query/body 检查。手动调用封闭 Pydantic 请求
schema，避免框架先返回请求格式差异；错误详情只含允许的字段路径/固定规则码，不含
输入值或库异常。重复 query/JSON 字段、额外字段、非 JSON 登录体均为 422。
GET 与 logout 不接受 body/query（list 只接受 limit/offset）；分页固定 created_at DESC、id DESC。

X-Request-Id 沿用契约 ASCII 白名单；无效时生成 UUID。所有 /api/v1 响应 no-store。
未实现路径为 404 RESOURCE_NOT_FOUND，已注册路径错误方法为 405 INVALID_REQUEST，
没有资源内容；它们不启用未来阶段。内部/数据库异常仅返回 500 INTERNAL_ERROR/request_id，
事务回滚，不将 SQL、连接配置或凭据传给普通日志。推荐启动命令和 Dockerfile 禁用
原始 URL access log，避免非法 query 携带凭据/客户内容时泄漏；使用安全 Audit 记录。
事务内部失败只在普通日志记录 INTERNAL_ERROR 与 request_id，不记录异常或 SQL 文本。

CORS_ALLOWED_ORIGINS 是明确 HTTP(S) origin JSON 数组，默认 []，禁止 *、credentials、
query/path/fragment；不使用 cookie。未知 Origin 的业务请求（含 preflight）直接拒绝，
不触发数据库。部署 HTTPS 与防暴破仍是部署审查事项；本阶段不加重试/缓存/限流系统。

## 验收

本地纯函数/HTTP 边界检查 + 真 PostgreSQL 的 API/存储事务测试。测试通过真实 ASGI
HTTP 请求操作真实隔离 schema，FixedClock 固定过期边界；不使用 SQLite 或 mock DB。
记录用户名/密码/角色隔离、token 摘要与退出、当前身份变更、相同拒绝响应、分页/封闭字段、
请求 ID/CORS/敏感错误、无 Provider 调用、事务回滚和数据库锁。已通过 CI 不等于人工 Review。
