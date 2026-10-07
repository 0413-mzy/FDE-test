# 2026-10-07 商城业务历史与本机查询验收

## 范围与代码基线

用户明确要求补齐业务修改历史并加入数据库，同时解释查看/查询方式。从入驻最终提交 `aea9f016714f41a2d31481ed9617e4a6be2c19fd` 建立 `codex/commerce-history-tracking`，依赖入驻 Draft PR #7。未合并 main、未部署、未接真实邮件/支付/物流或AI。

新增冻结0006与 `commerce_record_history`，29张业务表触发器记录允许字段的新增/修改/删除、实际数据库时间与事务内归因。公开认证请求在无法确认身份时保持匿名；直接SQL、种子与迁移标记来源。五张技术表不复制全行历史。历史表拒绝普通更新/删除/清空；数据库拥有者仍可改变结构。迁移不重写已有业务表，当前基线不冒充过去版本。

本机只读工具 `scripts/commerce-db.py` 支持表计数、结构、当前行、按表/UUID查询历史、私有CSV和默认只读psql；查询/导出过滤凭据。详细使用见[数据库说明](../database.md)。没有新增HTTP历史读取接口或跨客户权限。

## 本轮实际执行

| 检查 | 结果 |
| --- | --- |
| 后端完整真实 PostgreSQL：`pytest tests/database -m "not integration" -q` | 213 passed、11 deselected、0 skipped，183.87秒；收集时新增历史测试为10项 |
| 最终历史专项：`pytest tests/database/test_commerce_history.py -q` | 12 passed，8.89秒；包含全套收集后新增的售价/时间和审核归因两项；当前215项不同数据库测试均有通过证据，不把单次全套写为215 |
| 后端非数据库：`pytest -m "not integration and not database"` | 161 passed、248 deselected，1.69秒 |
| 后端 Ruff lint/format | 通过 |
| scripts unittest + Ruff lint/format | 9 passed；格式与lint通过 |
| 前端 test/lint/typecheck/build | 16 passed；lint/type/build通过 |
| 统一演示 all | 8个真实Chrome场景和8次API重启持久化检查通过 |
| 浏览器重启后的历史读取 | 全部8个独立schema保留订单历史、购物车删除历史；安全字段快照无密码/令牌摘要 |
| 原用户网址5179 | 真实Chrome目录→登录→注册可呈现，0 page errors |
| 原用户 API18008 | health、70商城操作、6身份及授权GET通过；保留原订单、店铺名、售后视图 |
| 独立审查 | 先规格符合性，再代码/安全审查；无阻塞发现。修正不支持历史的表应拒绝而不是静默返回空结果 |

新历史专项覆盖真实SQL前后值/删除/无变化/回滚、受控凭据变更、数据库实际观察时间、请求重放、追加表保护、0005→0006原值保存、29触发器、连接池上下文、公共注册验证、账户/地址版本与软删除、越权回滚、购物车结算删除、支付/退款及审核开店归因。既有数据库回归继续覆盖并发和业务约束。

浏览器8场景：purchase、partial-return、full-refund、shipped-partial-refund、return-no-restock、reject-withdraw、exceptions、onboarding。证据位于受保护的本机临时目录 `/private/tmp/fde-history-browser-evidence/results.json`；不上传账户、邮箱代码或凭据文件。

本轮没有重跑独立外部Sandbox HTTP集成，11项在数据库集合中明确 deselected；这不表示集成验收通过。Compose配置没有在本机运行，交给GitHub CI。历史测试及浏览器连接的是实际PostgreSQL17和实际本机HTTP服务，不用mock替代持久化验收。

## 现有运行数据库的真实升级

先暂停自己的API进程并生成0600私有 schema 备份，逐表保存升级前原值，再执行 `alembic upgrade head`。

- 原0005→0006成功；原有46张数据表逐行比较全部不变（迁移版本表单独更新）。
- 新增一张表，当前共有48张表（含迁移版本表）。29张业务表触发器全部存在。
- 升级瞬间产生134条 BASELINE：`before_data=NULL`、`changed_fields=[]`、`action=MIGRATION_BASELINE`；字段严格在允许名单内，无凭据快照。
- 原账户、订单、库存、消息、已注册用户及私有模拟邮箱保持；不重新播种或重置数据。
- 原API以后台独立进程恢复，前端保持原地址。授权读取和登录检查会正常产生会话/审计记录，因此134是升级瞬间的基线数量，不是此后所有历史的总量。

实际查询入口升级前核对47表、订单结构、9账户不输出密码摘要并确认计数不变；升级后核对48表、4订单基线、UUID过滤、不受支持表拒绝、0600CSV、psql只读/Malaysia时区与计数不变。

临时集群不是正式生产存储；本轮备份仍在受保护的本机运行目录。部署前应另行安排正式数据盘、独立备份保留和恢复演练。基线以前未保存的旧值无法恢复；行历史不能替代数据库备份。

## GitHub 交付

此记录描述本轮本机验收。依赖入驻分支的 Draft PR 会在交付时创建并附到聊天；准确提交的GitHub CI状态见该PR检查与描述，不能用上述本机结果替代。不会自动合并主分支。
