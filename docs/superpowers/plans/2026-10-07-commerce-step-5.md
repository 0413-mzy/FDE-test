# Commerce Step 5 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task; independent evidence/browser work uses dispatching-parallel-agents.

**Goal:** 将54项契约逐项关联执行证据，提供安全隔离且可重现的本机演示入口。

**Architecture:** 保持commerce-v1模块化单体。Python运行器管理独立schema与仅自身子进程；浏览器通过真实前后端执行，授权HTTP验证服务重启持久性。

**Tech Stack:** Python、PostgreSQL17、Alembic、FastAPI、Vite、Playwright、pytest。

## 1 覆盖审计
- [x] 映射54项到精确pytest节点，保存docs/commerce/step-5-coverage.json，记录剩余缺口。
- [x] 对遗漏权限/重复/异常边界在backend/tests/database/test_commerce_step5.py增加真实数据库断言。
- [x] 用TEST_DATABASE_URL执行商城专项，拒绝跳过。

## 2 可复现运行器
- [x] tests先验证scripts/commerce-demo.py的环境拒绝、唯一schema、随机密码、脱敏输出。
- [x] scripts/commerce-demo.py只创建commerce_demo_uuid；显式迁移/Seed，随机临时密码0600，启动自己的API/Vite。
- [x] 支持purchase、五种售后、exceptions、all；每场景全新schema；finally仅终止自身服务。
- [x] 浏览器完成后停止并重新启动自身API，授权HTTP读取客户订单和售后事实，比较重启前后内容。
- [x] 提供interactive模式保留服务直到CtrlC，用于手工复现。

## 3 异常页面
- [x] scripts/commerce-step5-browser-acceptance.cjs通过页面改价冲突/明确确认、付款失败重试、物流异常恢复。
- [x] 对每一新断言等待HTTP与页面事实，避免把睡眠当业务成功。
- [x] 运行七场景，保存脱敏JSON、截图和精确source commit。

## 4 完成交付
- [x] 更新AGENTS/README/范围/路线/开发说明，冻结旧历史记录。
- [x] 实际执行Ruff、前端test/lint/type/build、相关真实数据库测试、文档链接及diff检查。
- [x] 审查运行器安全和覆盖映射；提交推送并创建依赖第四步的Draft PR。
- [x] 发布并跟进准确head CI，初次lint失败已修正；最终结果以PR当前检查及交付报告为准。
