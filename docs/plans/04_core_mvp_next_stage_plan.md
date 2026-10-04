# 当前交付状态与下一阶段计划

同步日期：2026-10-03（Asia/Shanghai）。本文件是执行顺序与任务拆分，产品边界仍以
[01_core_plan.md](01_core_plan.md) 为准。用户随后授权开始下一阶段；当前已交付 Stage 1
契约文档包，待两名开发者 Review/合并。

后续授权更新：用户要求“自动执行并推进计划”。开始提交契约 PR，并在明确依赖该 PR 的
候选分支执行 Stage 2 数据库/Seed 与静态工作台。允许先准备依赖 PR，不把未合并契约称为
稳定 main 基线；人工 Review/合并出口保留，不自动合并。进度见 [执行日志](05_core_mvp_execution_log.md)。

## 1. 已确认基线

| 项目 | 当前证据 | 状态 |
| --- | --- | --- |
| Product Phase 0 | 仓库骨架、健康接口、前端外壳、CI | 已实现 |
| Product Phase 1：外部集成基础 | `2bfab022f0f7796aabfaa1eaf51978130419d575`；canonical snapshots、Clock、四个协议、HTTP adapters | 已实现；本次 70 tests passed，含 13 个真实 HTTP 测试 |
| 正式 main 基线 | `33857e2ac42472c690d583fc50e670d994f6a436`，PR #1 已合并 | 已包含 Phase 1；不是占位 README |
| 最新协作文档 | `docs/core-mvp-contracts`：`cc2f262`，[PR #2](https://github.com/Mark-UM/FDE-test/pull/2) | 契约已提交，CI 通过；待 Review/合并 |
| 外部 Sandbox S0–S1 | 独立仓库 main：`4131f1c4be7af6a6981e15379214d238228e8fa2` | 已提交；本次 fetch 后无新提交，工作区干净 |
| 远端 CI | [Product checks](https://github.com/Mark-UM/FDE-test/actions/runs/35831745007)：backend、frontend、compose 成功 | 验证的是上面的 main SHA；不包含真实 HTTP 集成测试 |
| main 保护 | branch protection API 返回 404，effective rules API 返回 `[]` | 待配置：PR review、必需 checks、禁止绕过直接 push |
| 容器运行 | 本机没有 Docker 命令；本次未构建/联启容器 | 待具备 Docker 的环境验证；不能用 compose config 代替 |

Product API 仍只有 `/health`。Stage 2 数据库/Seed 与静态工作台候选已准备；数据库有独立
PostgreSQL CI，工作台只展示虚构预计算数据。身份授权、Evidence/CaseContext 运行计算、AI、人工审核
工作流未实现。两人协作方案是 Core V1 的 MVP 子集，结束于人工批准；完整 Core V1
仍需后续模拟发送、幂等、审计和指标，不能把 MVP 验收表当作整个 Core V1 已完成。

详细证据见 [本次验证记录](../verification/2026-10-03-repository-sync-validation.md)。

## 2. 阶段编号与依赖

原始 Core 路线图的 Phase 1 是数据库/Seed，但已授权执行的 Product Phase 1 是外部集成。
后续使用协作方案的 **Stage** 编号，避免将同名阶段误认为已完成。

| 交付 Stage | 本次状态 | 对应原始路线图 | 下一步 |
| --- | --- | --- | --- |
| Stage 0：正式基线 | main 合并与 CI 已完成；保护和容器运行未完成 | Phase 0、已授权的集成 Phase 1 | 补齐治理/运行验证，保留未完成项 |
| Stage 1：Core MVP 契约 | PR #2 已提交，CI 通过；待两人 Review/合并 | 支撑原 Phase 1、2、4、5、6 | Review 后合并作为稳定依据 |
| Stage 2：数据库 / 工作台外壳 | 两条依赖契约的候选已实现；具体验证见执行日志 | 原 Phase 1、Phase 7 外壳 | Review 后 rebase main、改 base、重跑 CI 并合并 |
| Stage 3：身份授权与咨询 API | 2026-10-04 单独授权；[Draft PR #5](https://github.com/Mark-UM/FDE-test/pull/5) 候选及真 PG CI 已通过，待 Review | auth/Inquiry 读取；order 无 Context 返回 409 | 依赖审查/合并后，单独授权 Stage 4 |
| Stage 4：Evidence / CaseContext | 未开始 | 原 Phase 4 | 授权/API 与来源契约就绪后开始 |
| Stage 5：AI 草稿 / Validation / Review | 未开始 | 原 Phase 5、6、人工审核部分 | 只接收已授权、可追踪的 CaseContext |
| Stage 6：工作台 / MVP 端到端验收 | 未开始 | 原 Phase 7、10 的最小子集 | 正常及失败路径都通过，人工修改后重新校验 |

已有 Provider 与错误模型复用，不重建泛化 connector 框架。Sandbox 暂停扩展，源码/数据库
不并入 Product；不因为其无 API Key 就认为 Product 已具备用户授权。

## 3. 下一阶段目标与边界

**Stage 1 目标：形成两名开发者可以独立实现、互相测试的 Core MVP 契约包。**
交付是文档、接口示例和场景定义，不是 SQLAlchemy 模型、业务 API、AI 调用或 UI 实现。
具体决定已写入 [契约索引](../contracts/README.md)及六份文档；只有双方 Review 并合并后
才成为后续实现依据。本次文档检查不替代两人审查。

执行分支：继续 `docs/core-mvp-contracts`，PR base 为 `main`。main 已含完整 Phase 1，
无需再创建基线合并 PR。用户后续授权允许 Stage 2 候选先从契约分支创建；契约合并后
须 rebase 最新 main 并重跑 CI，不能省略人工审查。

## 4. 六项契约交付与验收

### T1：事实与业务数据所有权

建议交付 `docs/contracts/core-data.md`。数据负责人主笔，应用负责人审查。

- 先固定事实路径：优先复用现有 HTTP Providers；Product 保存本次处理所依据的快照与
  版本，Product Seed 只生成测试用户、咨询归属和工作流状态。若选择本地 facts fixture，
  必须通过同一 Provider 协议产生 canonical snapshots，不能让业务层绕开 Provider。
- 区分外部事实与 Product 工作流实体，不为演示复制完整订单/商城数据库。
- 定义 User/Role、Inquiry、取数记录/快照、Evidence、ContextVersion、DraftRevision、
  ReviewDecision、Audit/Integration 记录的最小字段、主外键、唯一性与 UTC 时间规则。
  此列表是候选概念，不代表每项必须单独成表；只引入能支撑 MVP 的实体。
- 明确外部 ID 与内部 ID 的映射，nullable 与缺失的区别；保留原 status、来源和源更新时间，
  Product 版本/抓取时间不覆盖源事实。订单数据不赋予权限。
- SQLAlchemy 2、Alembic、PostgreSQL 为后续实现目标；测试至少验证 PostgreSQL 迁移路径，
  SQLite 不能替代 PostgreSQL 的唯一性、并发或迁移验收。

验收：每个候选字段有拥有者与用途；每条关系/唯一性约束可写出正反例；双方确认事实路径，
后续数据库实现能支持业务查询且不直接访问 Sandbox SQLite。

### T2：Inquiry / Context / Draft / Review 生命周期

建议交付 `docs/contracts/core-lifecycle.md`。应用负责人主笔，数据负责人提供异常样本。

- 定义状态、合法转移、前置条件、操作者和失败后的状态，避免一次 HTTP 失败把咨询伪标为完成。
- 新取数生成新 Context 版本；草稿绑定确切 Context 与 Evidence 版本。
- 人工编辑产生新 revision 并重新执行 Validation；失效、失败或旧版本草稿不能沿用批准。
- 批准绑定最终文本、版本、操作者和时间，重复批准的幂等规则明确。
- MVP 的“已批准”与 Core V1 的“已模拟发送/已完成”不同；不复用 `SENT` 代表人工批准。

验收：有状态转换表和正常、失败、编辑后重验、旧版本批准、重复点击五类例子。

### T3：身份授权、API 与错误契约

建议交付 `docs/contracts/core-api.md`。应用负责人主笔，数据负责人审查越权测试。

- 固定最小登录/session 或 token 方案、密码存储、失效行为和测试用户配置；不设计企业 IAM。
- 固定 Agent 的 Inquiry 归属与订单关联授权。Supervisor 范围若进入 MVP，需显式团队边界；
  Admin 角色不能默认为所有业务订单的访问许可。明确每个入口的授权检查顺序。
- 定义登录/me、咨询读取、授权订单读取、resolve-context、草稿生成/编辑、批准等最小操作的
  请求/响应样例；只定义契约，不新增 routes。批准可先返回模拟工作流结果，不暴露发送操作。
- 定义 401、403、业务 not-found、source-not-found、timeout、unavailable、invalid-response、
  conflict、validation-failed 的区别。保留 request ID，禁止泄露源 payload/密钥。
- 查询无权或未知实体时的防枚举策略一致；前端 order ID、source facts 和声称的授权不可信。

验收：Agent A 访问 Agent B、修改 order ID、无订单 Inquiry、未登录、伪造授权有明确拒绝示例；
只有后端允许的范围可进入 Provider 调用/CaseContext。

### T4：Evidence / CaseContext 与数据质量契约

建议交付 `docs/contracts/evidence-case-context.md`。应用负责人主笔，数据负责人验证质量。

- Evidence 带稳定 ID、来源记录、快照版本、取值定位、源/抓取/发生时间，引用可精确回溯。
- 事实、来源原文、计划、未知、缺失、冲突分开。仓库自由文本的确定性处理仅保留可证明的
  来源信息，不凭字符串模式把一段计划自动提升为已发生事实。
- 固定各来源的查询结果与每个包裹 outcome：成功数据、成功空数组、记录不存在、无 tracking、
  timeout、unavailable、invalid response。一个包裹失败不丢弃其他包裹，也不产生物流异常结论。
- 源时间 null 表示 UNKNOWN；新 fetch 不证明最新业务状态。选择明确、可配置的 freshness
  规则与测试边界，发生时间不替代源更新时间；本阶段不实现缓存或重试。
- 统一 CaseContext 的最小授权范围、来源版本、缺失/冲突/风险字段。冲突保留双方来源，
  不自行决定仓库或物流一定正确。Unknown status 不归一化成成功/已交付。

验收：完整 JSON 样例覆盖正常、多包裹、旧数据、源失败、未知更新时间和冲突；同输入/Clock
产生确定结果；所有引用可定位；没有用未知信息补出承诺。

### T5：结构化 AI 输出与确定性 Validation / Review 契约

建议交付 `docs/contracts/analysis-review.md`。AI 负责人主笔，应用负责人审查安全门与调用顺序。

- 固定 intent、known_facts、plans_or_expectations、uncertainties、conflicts、missing_information、
  risk_flags、requires_human_review、reply_draft 及 Evidence 引用规则。
- AI 输入只来自授权 Context 版本；权限、事实、freshness 和动作由程序决定。
- 规定 schema/引用/旧数据/高风险/无依据确定性检查的失败结果和可恢复路径。
- 明确生成后与人工编辑后的 Validation 都是批准前置条件；高风险执行始终不可用。
- 定义 Fake LLM 失败样本与真实模型 eval 方式；不提前调用模型或增加 SDK。

验收：无效 ID、把计划当事实、忽视旧数据、退款完成声明、提示注入原文等失败样例均有明确
expected result；结构化结果不能自行获得发送/业务写入权限。

### T6：测试矩阵、实现交接与验收证据

建议交付 `docs/contracts/core-mvp-acceptance.md`。数据/测试负责人主笔，双方 Review。

- 将业务场景与来源场景编号分开，例如 `CORE-*` 与 `SANDBOX-Sxx`，不混用旧计划编号。
- 复用 S02 正常、S04 多包裹、S06 计划/未揽收、S07 旧数据、S08 504、S09 503、
  S10 shipment 404、S11 冲突、S12 未知订单；S01 的 200 + [] 用于成功空结果。
- 越权、恶意自由文本、无 tracking、部分包裹失败、未知状态、错误 AI、编辑后绕过批准等
  Sandbox 未提供的场景用 Product 层测试 fixture/Fake Provider；不能称作真实 Sandbox 覆盖。
- 集成测试固定 Clock 为 `2026-09-20T06:00:00Z`，使用独立临时 Sandbox；不 reset 共享服务。
- 每项写明入口、输入、预期结果、拒绝点、证据和负责人；用可验证结果代替“页面能打开”。

验收：六份契约相互一致、有成功和失败示例、无未决实现问题；两人完成审查后在 PR 中逐项
记录验收。代码/lint/build 检查保持通过；没有夹带业务实现。

## 5. 执行顺序与进入下一阶段的条件

1. 补 main 分支保护；在可用 Docker 环境记录容器构建/启动验证。契约写作可先进行，
   但 Stage 0 的未完成项保持可见，不宣称基线治理全部完成。
2. 双方先审 T1/T2/T3：事实路径、实体/状态、授权与 API 一致，作为 T4/T5 的前置输入。
3. 基于以上契约完成 T4，再审 T5；T6 随契约同步补齐，不先依赖一个不存在的 Context。
4. 两人确认并将契约 PR 合并 main。当前同步不创建 PR、不 push、不自动合并。
5. 数据负责人从更新的 main 创建 `codex/core-database`；应用负责人创建
   `codex/core-workbench-shell`。分工可以并行，但前端只依赖冻结的契约/静态 fixture，
   不把未合并数据库分支视作稳定依赖。
6. Stage 2 后再创建 `codex/order-inquiry-api` 与配套场景测试任务；订单快照读取依赖 Stage 4。

Stage 2 最小退出条件：空 PostgreSQL 可 migration、重复 Seed 不增殖、关系约束/数据版本可测；
前端外壳 lint/type/build 通过并展示 Loading/Empty/Error。业务授权/API 放 Stage 3；
Evidence 放 Stage 4；AI 放 Stage 5。此顺序是计划，后续实现需单独授权。

## 6. 已形成的决策与待审出口

- T1：现有 Sandbox HTTP + Product 不可变 canonical 快照；业务 Seed 不复制外部订单主库。
- T3：8 小时不透明 bearer session；Agent 自己分配、Supervisor 同 team、Admin 无业务读权；
  未知/无权 Inquiry 统一 403，订单访问必须先通过 Inquiry 授权。
- T4：fetch 30 分钟，源年龄订单/包裹/备注 24 小时、物流/事件 6 小时；null UNKNOWN；
  单包裹/仓库失败为局部 outcome，必需来源失败阻止 Context。
- T2/T5：新 run 使旧版本失效；编辑新 revision 重验；批准时重算时效并原子绑定文本/版本，
  同 key 同请求返回同 Approval；不产生发送/高风险执行。

这些决定已有明确契约和正反例，无需后续实现者猜测。六个完整 Product Context 示例与
30 项验收矩阵见 [契约包](../contracts/README.md)，本次机械检查见
[Stage 1 验证记录](../verification/2026-10-03-stage-1-contract-validation.md)。
人工 Review、PR 合并、main 保护及容器运行仍未完成；不自动推进 Stage 2。
