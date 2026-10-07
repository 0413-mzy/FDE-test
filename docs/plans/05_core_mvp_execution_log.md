# 项目决策与执行记录

## 2026-10-07：用户与商家入驻扩展

第五步已交付Draft PR #6后，用户选择先补用户/商家入驻，确认本地模拟邮件、部署前再接真实服务。
从f26b371建立codex/commerce-user-merchant-onboarding：新增注册恢复、账户资料/地址簿、
人工入驻审核与获批开店；六张新增表、18操作、私有模拟邮箱；旧账号/订单/库存原记录保持。
[契约](../commerce/onboarding.md)、[实施计划](../superpowers/plans/2026-10-07-commerce-onboarding.md)、
[本次验收](../verification/2026-10-07-commerce-onboarding.md)保存实际检查与故障边界。
实现6014da4已提交[Draft PR #7](https://github.com/0413-mzy/FDE-test/pull/7)，base为第五步分支。
本地后端364项、前端16项、八个浏览器场景通过；6014da4的push/PR全部8个CI检查通过。文档收尾后的准确HEAD在交付前再核对；不部署、不进入AI、不合并main。

## 2026-10-07：第四步消息与售后

用户明确请求“ok进行第四步吧”。从第三步0e50df5建立codex/commerce-messages-after-sales。
新增持久化通用/订单会话、双方消息、部分/全额未发退款、14天送达退货退款、
OWNER审批/接收/明确回库及DEMO退款结果；52个商城操作保持独立命名空间。
0004增量迁移保留既有订单/库存/支付/包裹/流水，原演示地址已升级。
补充订单店铺名称及手动模拟PENDING说明。没有真实资金/承运商/外部消息或AI，不合并main。

[实施计划](../superpowers/plans/2026-10-07-commerce-step-4.md)、
[切片](../commerce/step-4-implementation.md)、
[本次验证](../verification/2026-10-07-commerce-step-4.md)记录代码、浏览器、事务/权限与限制。
本地全套371通过；补充后的售后专项16通过；前端13通过；5个售后浏览器场景及原第三步双店回归通过。
实现提交2211c4a已交付[Draft PR #5](https://github.com/0413-mzy/FDE-test/pull/5)，依赖第三步PR #4。
最终CI状态以该PR当前SHA检查为准。

## 2026-10-06：第三步购买与履约

用户明确请求“开始第三部”。基于第二步89b988e建立codex/commerce-purchase-fulfillment。
新增独立商城模型/0003迁移、API与用户/商家/DEMO界面；保留旧客服接口和数据结构。
商品/库存、跨店下单、模拟支付、未付取消/到期、地址修订、分批发货、物流与收货为本步范围。
消息/退款/退货与AI未实现，不自动开始第四步、不合并main。

实现计划见[第三步计划](../superpowers/plans/2026-10-06-commerce-step-3.md)，
并发取舍与范围见[切片](../commerce/step-3-implementation.md)，
实际测试/浏览器/审查与CI见[验证记录](../verification/2026-10-06-commerce-step-3.md)。
实现da82e61已发布[Draft PR #4](https://github.com/0413-mzy/FDE-test/pull/4)，依赖第二步PR #3。
下列第二步“端点均不存在”是当时状态，不能替代第三步记录。

## 2026-10-06：第二步领域与规则

用户在第一步后明确表示“ok，下一步开始吧”。本次只交付领域设计，继承第一步分支，
不自动推进代码/UI或合并main。新增 [commerce-v1](../commerce/README.md)独立契约目录，
避免用旧客服core-mvp-v1定义客户/商家身份。

冻结多店独立Order、CNY整数分、15分钟库存预留、价格显式确认、独立财务/履约状态，
以及包裹数量、消息参与者、售后数量/退货窗口、模拟结果与幂等/并发规则。
API命名空间为/api/commerce/v1，端点全部仍是设计。验收分步骤③④⑤，所有场景NOT_RUN；
既有代码/迁移/Seed没有变化。验证见 [第二步记录](../verification/2026-10-06-commerce-domain-step-2.md)。


## 2026-10-06：电商平台重新定位，第一步

用户提出：先构建可交互电商系统，包含用户端、商家端及其业务关联，用户可查物流/发消息，
覆盖明确的真实业务场景，再考虑AI优化。随后要求重新设计仓库并明确批准“先开始第一步”。

决策：以多商家实体商品平台为默认方向，先采用模拟支付与物流。主线从客服 Evidence/AI
改为人工购物、交易、履约、消息与售后。更新活动主计划、范围、架构与开发约束；既有代码、
迁移、测试、启动说明和历史验证保留。商城领域规则/接口/UI尚未实现，本次不进入第二步。

本次文档检查及授权边界见 [第一步验证](../verification/2026-10-06-commerce-direction-step-1.md)。

重设计前的文档与代码可从不可变提交
[`a2e6bc1`](https://github.com/0413-mzy/FDE-test/tree/a2e6bc1b3862a1e732abc5388c9a90f0e6102da8)
查阅；Git历史不改写。新路线见 [阶段出口](04_core_mvp_next_stage_plan.md)。

---

## 以下为旧客服项目的历史记录

旧记录中的“禁止完整电商平台”“不开始Stage 4/5”等只记录当时授权，不再定义新平台范围。
代码兼容契约继续有效；旧PR编号多数属于Mark-UM上游，不能视作0413-mzy仓库的同号PR。

# Core MVP 自动执行日志

## 2026-10-06 Stage 4 委托

用户明确授权下一步由 Codex 全权负责。同步干净 main 至 `8469971` 后建立
`codex/core-evidence-context`，按冻结契约实现 Evidence/CaseContext。
交付与实际验收见 [Stage 4 验证记录](../verification/2026-10-06-stage-4-validation.md)，
设计与可执行边界见 [实现切片](../contracts/stage-4-implementation.md)。
旧记录保留原观察范围；不把旧“未授权 Stage 4”描述用于否定本次明确委托。

日期：2026-10-03。授权：用户要求“自动执行并推进计划”。产品边界以
[Core 计划](01_core_plan.md)为准，契约以 [Stage 1 包](../contracts/README.md)为输入。

## 当前执行范围

用户随后要求“自行审查并合并”，明确授权现有 PR #5 的自审与合并，取代此前禁止合并的出口。
自审覆盖身份/会话、权限、防枚举、事务/Audit、错误脱敏、配置及阶段边界，未发现阻断问题。
复核 Ruff 与 103 项本地测试通过；已核对代码 head `0193c38` 的四项 CI 和 91 真 PG。
本次新增改动只有授权/阶段状态及 [自审记录](../verification/2026-10-06-stage-3-self-review.md)，
不修改运行代码。合并按最终 head 的成功 CI 执行，实际合并结果见
[PR #5](https://github.com/Mark-UM/FDE-test/pull/5)。不声称独立开发者批准，不开始 Stage 4。

## 2026-10-06 整合与验证历史（自审/合并授权之前）

2026-10-06 用户要求检查并完成图片中的下一步：继续 PR #5 的 Stage 3，不重复开发。
远端 main 已包含契约 PR #2、数据库 PR #3 与修复 PR #6，SHA 为 `58aac36`。
本次已整合该 main，并新增数据库升级后既有会话/咨询权限的回归测试；同步 PR #5
base 已改为 main，新基线
[CI](https://github.com/Mark-UM/FDE-test/actions/runs/37450116062) 四项全部通过
（实现/测试提交 `cf421fd`）。Stage 3 仍待人工 Review/合并，不开始 Stage 4。

本地结果：91 项真实 PostgreSQL（57 数据库 + 34 API/事务），116 项后端回归（含
13 独立 Sandbox HTTP）全部通过；Ruff、前端 lint/type/build、Compose config 通过。
实际启动 Product Uvicorn + 隔离 PostgreSQL 17.11，五类账号范围 10/1/1/11/0，
详情、403/401、CONTEXT_REQUIRED 与退出撤销通过，重复 Seed 成功。
完整证据见 [Stage 3 main 整合验证](../verification/2026-10-06-stage-3-main-integration.md)。

## 2026-10-03 至 2026-10-04 执行历史

2026-10-04 用户明确授权“继续我的下一阶段”：新增 Stage 3 依赖候选
`codex/core-auth-inquiries` → `codex/core-database`，只交付后端身份会话与咨询读取。
不将第二阶段 PR 未合并误写为已在 main，不自动合并；Stage 4+ 未授权。

1. 检查/提交 Stage 1 文档，创建 `docs/core-mvp-contracts` → main 的审查 PR。
2. Stage 2 数据库候选：SQLAlchemy 2、Alembic、Product PostgreSQL schema、幂等虚构 Seed，
   真 PostgreSQL CI 测试。分支 `codex/core-database` 依赖契约 PR。
3. Stage 2 工作台候选：静态虚构数据，咨询列表/详情、逐包裹证据与质量、草稿审核布局，
   Loading/Empty/Error 展示。分支 `codex/core-workbench-shell` 依赖契约 PR。

本次授权允许先准备依赖契约的候选实现；不假称两名开发者已 Review，不自动合并 main。
Stage 3 的认证/业务 API、Stage 4 Evidence 计算、Stage 5 AI/Validation/批准行为不混入 Stage 2。
两条 Stage 2 PR 合并目标先为契约分支，契约合并后须 rebase main、改 PR base 并重跑 CI。

## 历史基线与验证环境

- origin/main 仍为 `33857e2`；远端已 fetch，无新业务提交；GitHub CLI 登录有效。
- 本机无 Docker、PostgreSQL executable/service；localhost:5432 无连接。
- 数据库验收在独立 CI PostgreSQL 服务执行，不以 SQLite/mock 或跳过结果替代。
- Stage 1 文档检查先运行；发现 AGENTS 中重复的 Stage 1 段落已去重。

## 历史状态（后续合并及本机环境变化见上方更新）

| 交付 | 状态 | 证据 |
| --- | --- | --- |
| Stage 1 契约 PR | [PR #2](https://github.com/Mark-UM/FDE-test/pull/2) 已提交，CI 通过 | `cc2f262`；六份契约、完整 fixture、文档验证记录 |
| Stage 2 数据库/Seed | [Draft PR #3](https://github.com/Mark-UM/FDE-test/pull/3)，CI 全通过 | `eeb9aca`；12 表、迁移/Seed、26 项真实 PostgreSQL 测试；[CI](https://github.com/Mark-UM/FDE-test/actions/runs/37109759410) |
| Stage 2 静态工作台 | [Draft PR #4](https://github.com/Mark-UM/FDE-test/pull/4)，CI 通过 | `d033d95`；13 项 Edge 与 Chromium 测试均通过；[最终 CI](https://github.com/Mark-UM/FDE-test/actions/runs/37129301879) |
| Stage 3 身份授权 / 咨询 API | [Draft PR #5](https://github.com/Mark-UM/FDE-test/pull/5)，CI 全通过，待 Review | `7c91dc7`；116 本地测试（含 13 真实 HTTP）+ 59 真 PG（含新增 33 项 API/事务）通过；[CI](https://github.com/Mark-UM/FDE-test/actions/runs/37178404364) |
| 人工 Review / main 合并 | 未完成 | 不由自动化代签 |
| main 保护 / 容器运行 | 未完成 | 不安装系统服务或修改仓库治理设置 |

每项完成后更新此日志与其验证记录。已提交历史验证文件保留原任务的观察范围。

## 当时的下一步与阶段出口

数据库候选本地 66 个单元 + 13 个真实 Sandbox HTTP 测试通过；26 个数据库测试在 CI
PostgreSQL 17 服务运行并全部通过。本机无 PostgreSQL，不将离线 SQL 生成视为数据库验收。
工作台候选只有本地预览行为；不取数、不产生 Evidence、不执行 Validation/批准/发送。
两条候选均依赖 Stage 1，审查和合并后才作为稳定基线。后续用户已单独授权 Stage 3
依赖候选；它继续保留人工 Review/合并出口，停止在身份与咨询 API，不开始 Stage 4。

第三阶段技术出口已通过，最新实现/验收见
[Stage 3 记录](../verification/2026-10-04-stage-3-access-validation.md)。下次若授权 Stage 4，
应先核对依赖审查/合并基线，再实现手动 resolve 的幂等 Run、Provider 来源记录、不可变
Evidence/Context、来源质量与失败归档，以及只读取当前 Context 的 order 入口。
必须真实 HTTP + FixedClock，保持权限在取数之前及提交前检查；不混入 AI、批准、发送、
重试或缓存。Stage 3 不调用 Provider，不能替代这些第四阶段验收。
