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

### GREEN：真实 PostgreSQL 修复后验证

实现提交 `d9251525381f8b111f04cd21e3037e7a26cc981c`：
[push CI run 37183226651](https://github.com/Mark-UM/FDE-test/actions/runs/37183226651)
全部四个任务成功，database job `111379810014` 为 **57 passed，51.55s，无 skips**。
backend 为 **66 passed，70 deselected**，Ruff lint/format 成功；frontend lint/type/build
和 Compose config 成功。
[PR CI run 37183228812](https://github.com/Mark-UM/FDE-test/actions/runs/37183228812)
也全部成功，验证同一实现提交。57 条包含原 26 条和新增 31 条；原文保留、增量迁移往返、
旧非法历史导致升级回滚均已执行。

### 改动清单与交接

- `backend/app/db/models.py`：七处 CHECK 使用一致的非空白条件。
- `backend/migrations/versions/0002_nonblank_constraints.py`：增量升级及降级 SQL，
  不导入当前 ORM，不改写 0001，不更新/删除业务行。
- `backend/tests/database/test_persistence.py`：28 个负例、原文保留、2 个迁移用例；
  迁移版本断言跟随 Alembic head；准确命名单事务乐观锁测试。
- `docs/contracts/core-data.md`：明确 Stage 2 与 Stage 3–5 验收职责。
- `README.md`：迁移行为、测试局限及本记录入口。
- `docs/verification/2026-10-03-stage-2-database-validation.md`：保留历史证据，追加澄清。
- 本记录：授权、基线、RED/GREEN、结果、限制与交接。

修复提交已验证通过，记录结果的后续提交仅修改文档。交付在
[草稿 PR #6](https://github.com/Mark-UM/FDE-test/pull/6)，base 为 `codex/core-database`。
未合并 PR #6/#3/#2，未修改队友分支或 main。下一步先审查/整合 #6，再按依赖关系
处理契约与数据库 PR；换 base 或同步 main 后必须重跑检查。

## 未完成项与操作限制

两个独立服务事务的并发、跨 Inquiry/team 语义授权、真实容器 build/start、外部 HTTP
集成测试未在本次修复验证；不把单事务乐观锁或 Compose config 当作对应运行证据。
旧库若存在非法历史，升级会报约束错误并停在 0001；需数据负责人在受控流程核查，
不得通过改写历史、禁用 trigger、自动删除数据来绕过。
本机未安装 PostgreSQL/Docker；数据库证据来自 CI 的独立可销毁 PostgreSQL 服务，
不运行用户数据库、不用 SQLite 替代。不改动 Provider、API、AI 或前端功能。
