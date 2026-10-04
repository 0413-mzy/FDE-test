# 数据库审查修复记录（2026-10-04）

## 授权与基线

用户确认修复审查问题并要求留痕。基于 PR #3 `baec664f4b913cfc4f771068c85dae88155688ee`，
新建 `codex/core-database-review-fixes`；不覆盖队友分支，不自动合并。
依赖 PR #2 契约；修复 PR 将以 `codex/core-database` 为 base。

## 问题及方案

- R1 / P2：默认 `btrim(value)` 只去普通空格，换行/制表符等空白值可通过七处非空约束。
  涉及 Inquiry 的 external_inquiry_id、external_order_id、escalation_reason，
  Run/GenerationAttempt/Approval 的 idempotency_key，以及 DraftRevision.reply_text。
  补 28 条空白输入负例（七字段 × 四种输入）和一条原文保留正例。
  计划使用 PostgreSQL POSIX 空白字符检查，只验证、不 trim、不修改合法原文。
- R2：同一事务内重复 UPDATE 仅验证乐观锁条件，不证明独立事务并发。
  计划修改测试名称和验收说明；真实并发/权限事务仍属后续服务阶段。
- R3：core-data §6 将同 Inquiry 引用列为 Stage 2 验收，与 §4 服务职责不一致。
  计划明确 Stage 2 验证外键目标存在，Stage 3–5 验证语义归属及事务边界。

## 验证轨迹

1. 先提交测试，保留原实现；GitHub PostgreSQL 17 任务验证修复前失败。
2. 观察到预期失败后再修复 ORM，新增增量迁移；不改写已冻结的 0001。
3. 重跑全套 CI，并在本记录追加真实结果和运行链接。

当前状态：回归测试已编写，等待 RED 验证；尚未宣称修复通过。
本机未安装 PostgreSQL/Docker；数据库证据来自 CI 的独立可销毁 PostgreSQL 服务，
不运行用户数据库、不用 SQLite 替代。不改动 Provider、API、AI 或前端功能。
