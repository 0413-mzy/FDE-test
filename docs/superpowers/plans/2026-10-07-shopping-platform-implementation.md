# 商品体验与平台运营实施计划

> 使用subagent-driven-development与dispatching-parallel-agents分离三个独立文件所有者；设计决定基于用户此前全权执行授权及本轮明确功能请求，不需重复确认常规实现选择。

Goal: 两个设计的数据库、授权事务API、真实交互UI和验收全部交付，现有数据保留。Architecture: 原模块化单体新增购物与平台领域，独立权限与有界图片存储，0007→0008增量迁移。Tech: FastAPI/SQLAlchemy/PostgreSQL/React/TypeScript/Pillow。

- [x] 商品后端owner：catalog_models.py/catalog_service.py/catalog_router.py/catalog_schemas.py、冻结0007、tests/database/test_commerce_catalog.py；不改其他owner文件。先失败测试再实现；明确API类型交给前端。
- [x] 平台后端owner：platform_models.py/platform_service.py/platform_router.py/platform_schemas.py、platform_seed.py、冻结0008、tests/database/test_commerce_platform.py；允许修改after_sales.py防争议竞争，其余公共文件交root集成；等待0007稳定后真实PG。
- [x] 前端owner：所有frontend/src、frontend/tests（root不并发改），购物图片分类筛选收藏评价、商家图片/回复/报表、平台完整工作台、客户/商家争议举报；先固定API契约对接，无假数据。
- [x] Root：app/main.py注册新router、models末尾导入新增模型、pyproject Pillow依赖、0007/0008migration元数据与history策略、旧catalog/merchantpublish/checkout可见性与限制边界集成，必要公用代码改动与owners协调。
- [x] Backend真实PG（全部隔离schema），pytest非DB、scripts、Ruff；前端test/lint/type/build；规格审查再质量审查；修复所有阻塞。
- [x] 新增真实HTTP/Chrome验收（购物体验+平台运营）及既有8场景回归；验证反向权限、失败路径、数据与history重启保持。
- [x] 原本机DB先私有备份，快照所有旧业务行，0006→0008升级仅新表及必要明确非改旧值字段；原行全部比对；新platform显式seed不提权旧账号。原网站恢复，新模块可操作。
- [x] 更新AGENTS/README/计划/范围/架构/启动/数据库指南及验证证据。依赖historyPR8的draftPR，attach；精确HEAD全部CI在交付前核验，不mainmerge/部署/AI。
