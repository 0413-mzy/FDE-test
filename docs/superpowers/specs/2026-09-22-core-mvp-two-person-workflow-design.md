# Core MVP 两人协作与 Git Branch 方案

## 1. 方案目的

本方案把 Core 产品计划缩小为一个可以运行、测试和演示的最小闭环，并规定两名成员的职责、交付顺序、分支用途、PR 规则和验收标准。

本轮只规划 **Ecommerce Order Support Assistant Core**。`DemoCommerce Sandbox` 不是当前开发目标；仓库中已有的 Sandbox Adapter 可以保留，但本轮不扩展 Sandbox、Scenario Engine、Policy API 或外部环境功能。

## 2. Core MVP 的固定范围

Core MVP 必须跑通：

```text
订单咨询
→ 后端权限检查
→ 读取订单及相关事实
→ 形成可追踪 Evidence
→ 生成最小授权 CaseContext
→ LLM 生成结构化回复草稿
→ 程序执行确定性 Validation
→ 人工查看、修改和批准
```

Core MVP 不包括：

- 自动退款、取消订单、修改地址、付款或赔偿；
- AI 自动发送客户回复；
- 通用 Agent 平台、CRM、ERP 或多租户 SaaS；
- Sandbox 功能扩展或真实第三方电商平台接入；
- 与上述闭环无关的重构和功能。

## 3. 两人职责

### 3.1 数据、测试与 AI 负责人

负责：

- 数据库概念设计和字段约束；
- SQLAlchemy 模型；
- Alembic 配置与 migration；
- 固定 Seed 数据及可重复导入；
- 数据库层测试；
- 正常、异常、权限、陈旧、缺失和冲突场景测试；
- LLM Provider 接入；
- 结构化 AI 输出模型和 Prompt；
- AI 评估数据集、unsupported claim 和不确定性测试；
- Core MVP 端到端验收。

不负责业务 Repository、API 或前端实现。AI 代码不能决定权限、修改事实、跳过 Validation 或绕过人工批准。

### 3.2 应用开发负责人

负责：

- Repository 和业务查询；
- Service 和 API；
- 登录、身份、授权和访问控制；
- Evidence 与 CaseContext 的确定性程序实现；
- Validation Layer；
- 人工审核和批准状态；
- React 客服工作台；
- 应用配置、部署和运行链路。

不直接改变已经冻结的数据库或 AI 数据契约。需要修改契约时，必须先由两人共同审查。

### 3.3 共同负责

- Core MVP 范围；
- 数据库与 API 契约；
- CaseContext 和 AI 输出契约；
- PR Review；
- 阶段验收；
- 最终演示和已知限制说明。

## 4. Ownership 边界

| 模块 | 主负责人 | 另一人的责任 |
| --- | --- | --- |
| SQLAlchemy / Alembic / Seed | 数据、测试与 AI 负责人 | 审查业务查询需要 |
| Repository / Service / API | 应用开发负责人 | 编写数据与异常测试 |
| 权限和业务规则 | 应用开发负责人 | 编写越权与绕过测试 |
| Evidence / CaseContext | 应用开发负责人 | 定义质量标准和验收样本 |
| LLM Provider / Prompt / Eval | 数据、测试与 AI 负责人 | 提供程序接口与配置支持 |
| Validation | 应用开发负责人 | 提供失败样本和评估要求 |
| React Workbench | 应用开发负责人 | 定义页面验收场景 |
| 端到端测试 | 数据、测试与 AI 负责人 | 修复应用问题并共同验收 |

## 5. Git 策略

### 5.1 长期分支

只保留一个长期稳定分支：

```text
main
```

`main` 必须保持可构建、可测试。两名成员不得直接向 `main` push；所有修改通过 PR 合并。

本方案最初从 `origin/phase-1-external-integration` 建立。2026-10-03 同步确认：Phase 1
已通过 PR #1 合并到 `main`（`33857e2`），不再是占位 README。当前协作文档仍在
`docs/core-mvp-contracts` 上；后续功能分支必须从更新后的 `main` 创建。具体任务见
[当前交付与下一阶段计划](../../plans/04_core_mvp_next_stage_plan.md)。

### 5.2 短期交付分支

分支按交付物命名，不按人员命名：

```text
docs/core-mvp-contracts
feat/core-database
feat/core-workbench-shell
feat/order-inquiry-api
test/order-inquiry-scenarios
feat/evidence-case-context
test/evidence-quality
feat/llm-draft-generation
feat/validation-review
feat/support-workbench
test/core-mvp-e2e
```

禁止使用长期个人分支，例如 `mark-branch`、`database-person` 或 `frontend-person`。一个分支只承载一个可以单独解释、测试和审查的交付物，合并后删除。

### 5.3 分支创建命令

在基线已经进入 `main` 后，每个新任务执行：

```sh
git switch main
git pull --ff-only origin main
git switch -c <branch-name>
git push -u origin <branch-name>
```

提交时只暂存明确文件：

```sh
git status
git add <file-or-directory>
git commit -m "<type>: <specific outcome>"
git push
```

不要使用无目标的 `git add .`，也不要把 `.env`、真实客户数据、密钥、数据库文件或 `.DS_Store` 提交到仓库。

## 6. 实施顺序

### Stage 0：建立正式基线

1. 验证 `phase-1-external-integration` 的后端、前端和 Compose 检查；
2. 通过 PR 把已验证基础合并到 `main`；
3. 为 `main` 启用 PR、状态检查和禁止直接 push；
4. 暂停 Sandbox 后续功能，只保留现有边界代码。

退出条件：`main` 包含可启动骨架，现有检查通过，README 准确说明当前状态。

2026-10-03 状态：基线合并、本地检查与远端三项 CI 已通过；main 分支保护尚未配置，
容器构建/联启尚未验证。Stage 0 不应标记为所有事项均完成；契约文档可继续推进。

### Stage 1：冻结 Core MVP 契约

分支：`docs/core-mvp-contracts`

共同定义：

- 最小数据库实体、主键、外键、唯一性和时间字段；
- Inquiry、Evidence、CaseContext、ReplyDraft 的生命周期；
- API 请求、响应和错误；
- CaseContext 输入边界；
- AI 结构化输出；
- Core MVP 验收场景。

退出条件：两人对契约完成 Review；没有 `TBD`、隐含权限或不明确的数据所有权。

2026-10-03 Stage 1 文档已按用户授权完成成稿：见 [六份契约与明确设计决定](../../contracts/README.md)。
它们尚待两名开发者 Review/合并；本次未开始 Stage 2。后续默认 `codex/` 分支前缀及
订单快照读取依赖 Stage 4 的调整，以 [当前执行计划](../../plans/04_core_mvp_next_stage_plan.md)为准。

### Stage 2：数据库与前端外壳并行

数据、测试与 AI 负责人使用 `feat/core-database`：

- SQLAlchemy、Alembic、第一份 migration；
- Core MVP 数据模型；
- 固定 Seed；
- 从空数据库 migration 测试；
- Seed 重复执行和关系完整性测试。

应用开发负责人使用 `feat/core-workbench-shell`：

- 页面结构和前端类型；
- API Client 接口；
- Loading、Empty、Error 状态；
- 只使用静态数据，不提前实现业务行为。

退出条件：数据库分支能从零创建并导入稳定数据；前端外壳能独立构建。

### Stage 3：订单和咨询读取

应用开发负责人使用 `feat/order-inquiry-api`：Repository、权限、Service 和 API。

数据、测试与 AI 负责人使用 `test/order-inquiry-scenarios`：正常订单、未知订单、多包裹、缺失数据、旧数据、冲突和越权场景。

退出条件：只有被授权的咨询可以读取相关订单事实；空结果、失败和未授权不会混淆。

### Stage 4：Evidence 与 CaseContext

应用开发负责人使用 `feat/evidence-case-context`，实现确定性转换：

```text
authorized source facts → Evidence → CaseContext
```

数据、测试与 AI 负责人使用 `test/evidence-quality`，验证来源、时间戳、缺失、冲突、陈旧状态和最小授权范围。

退出条件：每个重要结论都能追踪到 Evidence；未经授权或不可靠的内容不能进入 CaseContext。

### Stage 5：AI 草稿与 Validation

数据、测试与 AI 负责人使用 `feat/llm-draft-generation`：LLM Provider、结构化输出、Prompt、Fake Provider 和 eval 数据集。

应用开发负责人使用 `feat/validation-review`：Schema、Evidence 引用、新鲜度、高风险意图和 unsupported certainty 检查，以及人工审核状态。

退出条件：模型只能基于 CaseContext 生成草稿；无效或无依据输出不能进入人工批准步骤。

### Stage 6：工作台和端到端验收

应用开发负责人使用 `feat/support-workbench`，连接真实 Core API 并实现证据查看、草稿编辑和人工批准。

数据、测试与 AI 负责人使用 `test/core-mvp-e2e`，验证完整闭环、失败路径、审计信息和演示脚本。

退出条件：核心流程可以在本地重复运行，关键失败可观察，没有自动高风险操作或自动发送。

## 7. 并行开发规则

- 只有没有代码依赖的工作才并行；依赖尚未合并的分支不能假装依赖已经稳定。
- 数据库模型合并前，应用负责人只能根据已冻结契约建设前端外壳或接口类型。
- AI 分支开始前，CaseContext 契约必须合并。
- 前端连接真实 API 前，API 响应与错误格式必须合并。
- 测试可以先于实现编写，但测试 PR 应清楚标注预期失败原因和依赖分支。
- 如果必须基于另一个未合并分支工作，应明确记录 base branch；上游合并后立即 rebase 到 `main`。

## 8. PR 与 Review 规则

每个 PR 必须写明：

1. 解决的问题；
2. 明确不解决的内容；
3. 影响的模块和契约；
4. 测试命令与实际结果；
5. migration、数据兼容性或安全影响；
6. 已知限制和后续工作。

Review 责任：

- 数据库、Seed、AI 和测试 PR：应用开发负责人 Review；
- API、业务、权限、Validation 和前端 PR：数据、测试与 AI 负责人 Review；
- 契约变化必须两人明确同意；
- PR 未通过对应检查不得合并。

## 9. 冲突避免规则

- 数据库负责人主改 `backend/app/models/`、`backend/alembic/`、Seed 和数据库测试；
- 应用负责人主改 Repository、Service、API 和 frontend；
- 共享 Schema 或契约先在独立 PR 中变更，再由双方分支同步；
- 不在同一个长生命周期分支上混合数据库、API、AI 和 UI；
- 开始工作前更新 `main`，提交前检查 diff，PR 合并后删除分支；
- 发现契约变化时暂停下游实现，先合并契约修订。

## 10. Core MVP Definition of Done

只有以下条件全部满足，才称为 Core MVP 已跑通：

- 数据库可从零 migration；
- Seed 可重复运行且关系正确；
- 权限由后端执行并有越权测试；
- 订单、咨询及相关事实可读取；
- Evidence 包含来源和时间信息；
- CaseContext 仅包含最小授权证据；
- LLM 返回结构化草稿；
- Validation 能拦截无效引用、高风险意图和无依据确定性；
- 人工可以查看证据、修改并批准草稿；
- 正常、缺失、陈旧、冲突、失败和越权场景有测试；
- 前后端、数据库和 AI 能在本地完成一次可重复演示；
- README 准确区分已实现、计划中和明确不做的能力。

该 Definition of Done 不表示生产就绪。真实客户数据、真实发送、真实外部平台、生产安全、监控、备份和运营采用仍需单独验证。
