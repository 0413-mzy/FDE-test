# Commerce Platform · 可交互电商业务平台

先把用户与商家之间的电商业务做通，再通过实际使用发现 AI 可以优化的环节。
目标平台以多商家、实体商品为起点，支付和物流先模拟；订单、库存、消息与售后的
数据关联和状态变化由后端处理并持久化。

> 2026-10-07：第四步新增双方消息、部分退款与退货退款，用户、商家和模拟事件控制台
> 连接同一 PostgreSQL。实际验收以 [第四步验证记录](docs/verification/2026-10-07-commerce-step-4.md)
> 为准。候选交付为 [Draft PR #5](https://github.com/0413-mzy/FDE-test/pull/5)，依赖第三步PR #4。
> 支付、物流和退款是模拟；本分支不合并 main。

## 目标体验

用户浏览商品、加入购物车、下单并模拟付款；商家看到订单、处理并发货；用户查看
包裹物流、联系商家、确认收货或申请售后。两端操作连接同一套业务数据。

```text
用户端 ── 商品 / 购物车 / 订单 / 物流 / 消息 / 售后 ──┐
                                                   ├─ 平台后端 ─ PostgreSQL
商家端 ── 商品 / 库存 / 订单处理 / 发货 / 消息 / 售后 ─┘
                              │
                       模拟支付与物流适配器
```

## 已有成果与目标能力

| 内容 | 当前状态 | 新方向中的用途 |
| --- | --- | --- |
| FastAPI、React/TypeScript、Compose、CI | 已有基础 | 保留工程框架 |
| PostgreSQL、迁移、Argon2id、服务端会话 | 客服基础与独立商城账号均已实现 | 复用原语；客户/店铺权限保持域隔离 |
| Inquiry API、权限与审计 | 已有客服实现 | 保持兼容，不冒充订单管理系统 |
| Providers、外部 Sandbox HTTP 适配 | 已有 | 保留集成与故障测试能力 |
| Evidence / CaseContext、历史与恢复 | 此分支继承 Stage 4 候选 | 保留为未来客服/AI辅助模块 |
| 用户端、商家端、商品/库存/购物车/购买/履约 | 第三步新增实现 | 新平台主线；支付与物流为模拟 |
| 网页与后端业务交互 | 已接入 commerce-v1 API | 无前端假业务数据 |
| 消息、退款与退货 | 第四步新增实现 | 双方纯文本消息、OWNER审核、模拟退款及回库 |
| AI 回复、推荐、自动化 | 尚未实现 | 在人工业务闭环之后评估 |

已有 Stage 4 的 316 项测试记录只证明客服基础的对应实现，不能证明新平台已完成。
主分支与候选分支状态以 GitHub 为准；本次不合并 main。

## 开发顺序

1. **重新定位与约束（已交付）**：产品目标、范围、架构、复用决策和阶段出口。
2. **业务模型与规则（已交付）**：用户/店铺权限、商品/SKU、库存、订单、支付、包裹、消息、售后
   的关系与状态规则，以及双端验收场景。
3. **购买与发货闭环（第三步实现）**：建设用户端与商家端，连接同一后端和数据库。
4. **消息与售后闭环（本次实现）**：双方沟通、取消、退款和退货。
5. **异常覆盖与演示**：缺货、重复请求、拆包、支付失败、物流延迟等可复现场景。
6. **AI 机会评估**：用操作记录和痛点决定是否增加 AI，单独设计和验收。

## 文档入口

- [产品主计划](docs/plans/01_core_plan.md)：新的产品定位与目标闭环。
- [电商领域契约](docs/commerce/README.md)：commerce-v1的数据、权限、状态、API与验收。
- [范围与阶段边界](docs/scope.md)：平台目标和本次实际交付的区别。
- [目标架构与已有模块](docs/architecture.md)：数据所有权和模块关系。
- [阶段路线与验收](docs/plans/04_core_mvp_next_stage_plan.md)：每步的可验证产出。
- [决策与执行记录](docs/plans/05_core_mvp_execution_log.md)：本次变更及历史。
- [当前代码启动与验证](docs/development.md)：迁移、商城 Seed、双端启动与演示流程。
- [既有客服契约](docs/contracts/README.md)：兼容参考，不是新平台产品范围。
- [外部 Sandbox 的定位](docs/plans/03_ecommerce_environment_plan.md)：可选集成环境。

## 仓库结构

```text
backend/             商城领域与 API、新增迁移/测试；保留兼容客服模块
frontend/            React + TypeScript + Vite 用户端、商家端、模拟控制台
docs/plans/          产品主计划、路线及执行记录
docs/commerce/       电商领域契约及第三/四步实现边界
docs/contracts/      既有客服模块的冻结契约与示例
docs/verification/   指定日期/版本的验证证据
AGENTS.md            当前开发约束
.env.example         开发配置示例，无真实凭证
docker-compose.yml   开发环境配置；不是生产部署
```

原客服范围已退出项目主线。既有代码、接口、迁移与验证记录保留；未来平台能力必须
通过新增业务规则、真实持久化和双端交互交付，不能用页面占位或假状态代替。

## 第五步：可复现本机演示

用户已授权场景完善，部署以后考虑。新增统一入口自动创建独立schema、迁移和虚构账号，
启动自己的API/前端，执行购买、五种售后和异常恢复；不会清空现有订单。
先安装backend开发依赖和frontend的npm依赖，显式配置APP_ENV与隔离TEST_DATABASE_URL。

```sh
python scripts/commerce-demo.py --scenario interactive
python scripts/commerce-demo.py --scenario all
```

interactive输出本地网址及仅本机可读的随机密码文件，CtrlC停止自己的服务并保留数据。
交付见[Draft PR #6](https://github.com/0413-mzy/FDE-test/pull/6)与[第五步验收](docs/verification/2026-10-07-commerce-step-5.md)。
all还需Playwright和Chrome，详见[开发说明](docs/development.md#第五步统一演示入口)。
覆盖清单区分通过和细项缺口；本步不部署、不合并main、不加AI。
