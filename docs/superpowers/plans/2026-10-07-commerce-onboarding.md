# Commerce Onboarding Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans; dispatching-parallel-agents authorizes isolated backend/frontend/browser subtasks.

**Goal:** 新用户能验证注册、恢复账户、管理资料/地址，并申请通过审核后成为现有商城店主。

**Architecture:** 现有commerce独立增量命名空间、0005迁移，严格对象权限和事务；本机受保护模拟邮箱。

**Tech Stack:** FastAPI、SQLAlchemy、Alembic、PostgreSQL、React/TypeScript、真实Chrome。

## 1 后端
- [x] 先在backend/tests/database/test_onboarding.py写注册/恢复、权限、资料/地址、入驻审核用例并观察RED。
- [x] 新backend/app/commerce/onboarding.py、onboarding_router.py、onboarding_models.py，新增0005；旧迁移冻结。
- [x] app/main.py接入新router；独立DTO/幂等记录和严格匿名限额，禁止公开验证码与自授角色。
- [x] app/commerce/mailbox.py窄投递适配/CLI，本机目录0700文件0600；app/core/config.py显式邮件目录。
- [x] 显式onboarding_seed初始化独立reviewer，不覆盖旧账号资格或密码。
- [x] 真实PG强制争用、密码重置撤销旧会话、错误/过期/重复码、默认地址/数量限额、历史快照与回滚测试GREEN。

## 2 前端
- [x] frontend/src/Account.tsx（认证、账户、地址簿和申请/审核组件）接冻结API，沿用现有设计。
- [x] App.tsx新增注册/验证/恢复入口、账户中心与受审核资格控制的审核页。
- [x] ui.AddressForm保持可选受控草稿接口；Customer.CartPage增加本人地址簿预填，已有草稿恢复不退化。
- [x] 获批刷新/auth/me更新店铺，改密码成功清理本地会话；不存在自动提交新权限。
- [x] 前端相关规则测试先RED后GREEN，lint/type/build无误。

## 3 演示和验收
- [x] scripts/commerce-onboarding-browser-acceptance.cjs真实UI完成注册验证→资料地址→申请→审核批准→上架购买。
- [x] 脚本仅环境操作者读取模拟邮箱目录；不得通过HTTP返回code，所有业务写入经UI。
- [x] scripts/commerce-demo.py新增onboarding独立场景，显式本机邮箱和reviewerSeed，重启仍保留事实。
- [x] 新/旧商城专项、非DB单元、前端、Ruff、文档链接以及原购买/售后浏览器回归通过。
- [x] 原库增量升级前后完整订单/库存快照相同；使用原配置重启供用户本机体验。
- [ ] 独立审查、草稿PR依赖第五步、准确head CI验证。不合并main，不部署、不进入AI。
