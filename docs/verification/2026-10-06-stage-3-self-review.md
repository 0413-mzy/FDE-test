# Stage 3 自审与合并记录

日期：2026-10-06。用户明确要求“自行审查并合并”，授权自审后通过
[PR #5](https://github.com/Mark-UM/FDE-test/pull/5) 合入 main，取代之前的禁止合并限制。
本次是 Codex 自审，不代表两名开发者独立 Review 或 GitHub APPROVED。
GitHub PR 的最终状态、合并时间及提交是合并结果的权威记录。

## 审查结果

未发现阻止 Stage 3 合并的问题；运行代码与测试未作额外修改。
审查基准为 `0193c38636bc7760af86e95fe8a9c5e516c1ef10`，已包含 main `58aac36`；
随后只补充授权、阶段状态和本记录，合并前继续核验最终 head 的 CI。

| 审查范围 | 结论与证据 |
| --- | --- |
| 登录与会话 | Argon2id 参数沿用数据库契约；密码不 trim；固定八小时；只存 token 摘要；退出仅撤销当前会话 |
| 当前身份与授权 | 每个请求查当前 active/role/team；Agent 仅本团队本人分配、Supervisor 本团队、Admin 无业务权限 |
| 防枚举与输入 | 认证先于字段检查；未知/无权 UUID 同形 403；重复或额外字段拒绝；错误不回显输入 |
| 事务与 Audit | User → AuthSession → Inquiry 锁序；登录/退出与 Audit 同事务；真实 PG 验证失败回滚和独立连接锁竞争 |
| HTTP 与配置 | API no-store/request ID；显式 CORS；禁用原始 URL access log；异常不披露 SQL/连接参数；health 与启动不连接数据库 |
| 产品边界 | order 只检查授权/绑定并返回 CONTEXT_REQUIRED；无 Provider/AI/高风险动作；Stage 4 路由未暴露 |

## 验证证据

- 本次复核：`python -m ruff check --no-cache .`、
  `python -m ruff format --check --no-cache .` 通过，38 个文件格式正确。
- 本次复核：`python -m pytest -m "not integration and not database" -q -p no:cacheprovider`，
  **103 passed，104 deselected，2 项依赖弃用 warning**。
- [代码 head 的 CI](https://github.com/Mark-UM/FDE-test/actions/runs/37450552463)：
  backend/database/frontend/compose 四项成功；数据库日志确认 **91 passed，71.57s**。
- 复用紧接此前完成的 [main 整合验证](2026-10-06-stage-3-main-integration.md)：
  本地 91 真 PG、116 非 DB（含 13 独立 Sandbox 真实 HTTP）及实际 Product HTTP 验证通过。
  本次没有更改相应代码，不重复声称这些是新的本地执行。
- 合并只通过普通 PR 流程，在最终 head 的检查全部成功后执行；不直接 push main、
  不使用 admin 绕过、不强制推送，不改动用户既有 `output/` 报告。

## 保留的未完成范围

静态工作台 PR #4、main 分支保护、完整 Compose build/start 与生产 HTTPS/登录防暴破
部署评审仍未完成。自审与本阶段合并不表示完成部署或整个 Core V1。
Stage 4 Evidence/CaseContext、AI、前端登录及草稿/审核/发送均不在本次授权中。
