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
  使用 PostgreSQL POSIX `[:space:]` 空白字符检查，只验证、不 trim、不修改合法原文。
  ORM 与新增 `0002_nonblank_constraints.py` 保持一致，冻结的 `0001_core_mvp.py` 未改。
  新增两条迁移测试：带合法历史数据 up/down/up 后文本/摘要/引用不变；旧非法历史数据
  导致升级失败、版本回滚且原文保持，不自动清洗或绕过历史保护。
- R2：同一事务内重复 UPDATE 仅验证乐观锁条件，不证明独立事务并发。
  已修改测试名称、README 和历史验收说明；真实并发/权限事务仍属后续服务阶段。
- R3：core-data §6 将同 Inquiry 引用列为 Stage 2 验收，与 §4 服务职责不一致。
  已明确 Stage 2 验证外键目标存在，Stage 3–5 验证语义归属及事务边界。

## 验证轨迹

1. 先提交测试，保留原实现；GitHub PostgreSQL 17 任务验证修复前失败。
2. 观察到预期失败后再修复 ORM，新增增量迁移；不改写已冻结的 0001。
3. 重跑全套 CI，并在本记录追加真实结果和运行链接。

### RED：真实 PostgreSQL 复现

测试先行提交 `160e01b966258b7d41f85f886fa57fce596323d8`（尚无实现修复）。
[CI run 37183067706](https://github.com/Mark-UM/FDE-test/actions/runs/37183067706)
database job `111379343775`：**21 failed、34 passed，46.74s，无 skips**。
21 个 tab/newline/混合空白负例均为 `DID NOT RAISE IntegrityError`；七个普通空格负例
和合法原文正例通过。backend、frontend、Compose 任务成功。这是预期 RED，不是环境失败。

### 本地修复后检查

临时隔离 Python 3.12 环境 `/private/tmp/fde-review-venv`，从 `backend/` 执行：

```sh
ruff check .
ruff format --check .
pytest -m 'not integration and not database' -q
```

结果：lint 通过、30 个文件格式通过、**66 passed，70 deselected**。
deselected 包含 13 个外部 HTTP 集成测试和 57 个 PostgreSQL 测试，不当作通过证据。

当前状态：实现已修改，等待 GREEN 的真实 PostgreSQL CI；尚未宣称修复通过。
本机未安装 PostgreSQL/Docker；数据库证据来自 CI 的独立可销毁 PostgreSQL 服务，
不运行用户数据库、不用 SQLite 替代。不改动 Provider、API、AI 或前端功能。
