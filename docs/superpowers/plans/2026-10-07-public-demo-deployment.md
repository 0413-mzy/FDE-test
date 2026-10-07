# Public Demo Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Independent backend/frontend owners; root owns packaging, integration, QA and publication. No main merge.

**Goal:** 在每月100元人民币以内发布保留模拟交易的持久化电商演示，并保持本机数据。
**Architecture:** 单容器同源静态网页+FastAPI，独立Neon PostgreSQL，Render HTTPS；显式公开演示开关、共享虚构账号和私密管理账号。
**Tech Stack:** React/Vite、FastAPI、PostgreSQL、Docker、Render/Neon。

- [ ] 后端owner：新增app/commerce/public_demo.py、public_demo_seed.py及测试；配置app/core/config.py/cloud URL规范化app/db/connection.py；拒绝邮件/密码/资料/入驻写入，明确public demo开启模拟route，单进程限流/静态资源/readiness/安全头。GET demo-info契约enabled/accounts/password；默认关闭返回enabled=false/accounts=[]/password=null。root集成main.py，seed脚本禁止日志泄露。
- [ ] 前端owner：frontend/src及tests；读取demo-info，醒目标记模拟/共享/虚构信息，展示访客账号与公开密码，隐藏注册/邮件/密码/入驻修改，仅保留公开演示下资料读取、地址与业务；同源空apiBase。默认本机行为不变。test/lint/type/build。
- [ ] root：deployment/Dockerfile、启动模块、render.yaml、.dockerignore、生产Compose、部署文档/CI；Docker build并测试production单容器/实际DB，不改原本机数据库。账号未初始化则显式seed，相符重启保持，拒绝密码错配和非空不明数据库。
- [ ] 先有意义失败测试再实现：关闭默认模拟生产、公开demo阻止敏感账号流程且保留权限、管理密码不泄漏、匿名demo401、静态源码不可读、启动拒绝错误配置、重启保持记录。
- [ ] root规格/代码审查与回归；生产HTTP/真实浏览器购买、物流与图片；backend/scripts Ruff/pytest、frontend全套、云Blueprint schema及Docker CI。
- [ ] root公开发布：等用户账号登录/付款配置，不替用户接受协议或设置认证密码。独立云库初始化，发布准确候选SHA，验证HTTPS/持久数据、权限和实际账单；提供URL/保密管理员资料路径/备份说明。
- [ ] root GitHub草稿PR依赖PR9，attach、精确HEAD CI、文档状态与真实发布状态保持一致；未完成云登录不可声称上线。
