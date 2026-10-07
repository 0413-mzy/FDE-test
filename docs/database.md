# 本机查看数据库与变更历史

商城的数据保存在 PostgreSQL，而不是浏览器缓存。本机开发数据库没有公开查询网页；可用下面的终端工具查看。网站账户与数据库连接账户是两套身份，不需要把网站密码填进数据库工具。

## 当前机器：直接查询

在项目根目录打开终端，运行：

```bash
/private/tmp/fde-review-venv/bin/python scripts/commerce-db.py --local-demo --tables
/private/tmp/fde-review-venv/bin/python scripts/commerce-db.py --local-demo --describe commerce_orders
/private/tmp/fde-review-venv/bin/python scripts/commerce-db.py --local-demo --rows commerce_orders --limit 10
/private/tmp/fde-review-venv/bin/python scripts/commerce-db.py --local-demo --history commerce_orders --limit 20
```

第一条列出表和记录数；第二条查看字段；第三条查看订单当前值；第四条查看订单的历次变化。`--history commerce_account_profiles` 查看资料版本，`--history commerce_address_book` 查看地址版本，`--history commerce_skus` 查看价格等商品规格变化。加 `--id <记录UUID>` 只看某一条业务记录，`--offset 20` 翻页；单次最多100条。

`--connection-info` 显示数据库名称、连接位置和当前 schema，不输出连接密码。本机当前数据库名为 `fde_commerce_validation`，开发账户为 `fde_commerce_test`，通过本地 Unix socket 连接。工具从已有受保护的运行配置取得当前 schema，避免误查测试 schema。这个临时开发集群不等于正式部署数据库；删除临时目录会丢失数据，因此部署前需要安排正式存储和备份。

导出示例（文件包含业务信息，请保存在自己的目录）：

```bash
/private/tmp/fde-review-venv/bin/python scripts/commerce-db.py --local-demo --rows commerce_orders --limit 100 --export /private/tmp/commerce-orders.csv
```

导出文件权限为0600，已有同名文件不会覆盖。查询工具以只读事务执行固定查询，并过滤密码摘要、令牌摘要及验证码等字段，同时省略BYTEA图片内容；它不提供修改或删除数据的命令。

上面的 Python 路径是当前机器已有的开发环境。其他机器安装后端开发依赖（在 backend 目录运行 `python -m pip install -e ".[dev]"`）后，使用自己的 Python，并通过 `--runtime-file /自己的受保护路径/runtime.json` 或环境变量 `DATABASE_URL` 指定连接；不要把包含密码的连接字符串贴到聊天、源码或截图中。

## 想自己写 SQL

```bash
/private/tmp/fde-review-venv/bin/python scripts/commerce-db.py --local-demo --psql
```

进入 PostgreSQL 终端后，可以输入：

```sql
\dt commerce_*
\d commerce_orders
SELECT id, title, status, updated_at
FROM commerce_products ORDER BY updated_at DESC LIMIT 20;
SELECT id, status, total_minor, currency, created_at, updated_at
FROM commerce_orders ORDER BY created_at DESC LIMIT 20;
SELECT id, entity_table, entity_id, operation, actor_username,
       action, reason, recorded_at, changed_fields, before_data, after_data
FROM commerce_record_history
WHERE entity_table = 'commerce_orders'
ORDER BY id DESC LIMIT 20;
\q
```

`\dt` 列出表，`\d` 看结构，`\q` 退出。金额采用最小货币单位（例如100分=1元），并与币种一起解释。时间字段带时区；这个 psql 入口按马来西亚时间显示。普通查询入口输出保留原时间的时区信息。

psql 默认开启只读，方便安全查询，但连接仍是开发数据库拥有者，并没有变成受限的新角色：有经验的人可以主动关闭只读或修改结构。直接 SQL 也不会经过查询工具的敏感字段过滤。日常查看建议优先使用上面的固定查询命令。

## 各类表保存什么

| 部分 | 主要表 | 内容 |
| --- | --- | --- |
| 账户与入驻 | accounts、account_profiles、email_challenges、merchant_applications、shop_memberships | 登录身份、资料、验证摘要/有效期、入驻申请和审核、店铺权限 |
| 地址 | address_book、address_revisions | 当前地址簿；订单地址快照及修订 |
| 商品与库存 | shops、products、skus、inventory、stock_reservations、stock_movements | 店铺、商品、规格价格、库存、占用与库存流水 |
| 购买与支付 | carts、cart_lines、checkouts、orders、order_lines、payment_attempts | 购物车、结算、订单、购买时价格/商品快照、模拟付款尝试 |
| 履约 | shipments、shipment_lines、tracking_events | 发货包裹、对应商品、模拟物流节点 |
| 消息与售后 | conversations、messages、after_sale_cases、after_sale_lines、refund_attempts、return_shipments | 会话消息、退款/退货申请及审核、模拟退款、退货物流 |
| 技术与操作记录 | sessions、business_audits、idempotency_records、simulation_events、anonymous_requests、auth_rate_events | 会话、操作审计、防重复、模拟调度、匿名防重复与限流 |
| 商品购物体验 | categories、product_experiences、product_images、favorites、product_reviews | 分类、商品额外信息与平台限制、规范化图片、私有收藏、购买评价与商家回复 |
| 平台运营 | platform_roles、moderation_reports、moderation_actions、disputes | 独立平台资格、举报、处理决定、售后争议及双方证据和仲裁 |
| 新增历史 | record_history | 业务记录的新增、修改、删除与升级时基线 |

本机本轮升级至0008，当前共57张表（包含迁移记录及保留的旧客服表）。升级与平台seed保留每一条旧记录，见[验收记录](verification/2026-10-07-shopping-platform.md)。

上述表名均以 `commerce_` 开头。旧客服模块的表单独保留，不与商城业务混用。

## 新历史表怎样解释

增量迁移0006最初给29张商城业务表添加数据库触发器；本轮0007/0008给9张新增商品/平台业务表接入同一机制，当前38张业务表。每次真正写入都会与业务事务一起保存历史；事务回滚时历史一起回滚。同一次事务内的多个真实状态变化可以形成多条历史，重复请求没有业务写入时不会凭空增加历史。

`commerce_record_history` 包含：

- `entity_table` / `entity_id`：哪张表的哪条记录。
- `operation`：BASELINE（升级基线）、INSERT（新增）、UPDATE（修改）、DELETE（删除）。
- `before_data` / `after_data`：修改前后允许保存的业务字段；删除仍保留删除前快照。
- `changed_fields`：发生变化的字段名。
- `actor_id` / `actor_username`：通过身份与权限检查后确定的操作者；匿名操作或直接 SQL 可以为空。
- `db_role` / `request_id` / `action` / `reason`：数据库角色、请求编号、操作来源及已有业务理由；没有理由时为空，不编造。
- `recorded_at`：数据库实际记录时间，与业务记录里的创建/更新时间、物流事件发生时间分别保存。

历史使用明确的字段白名单；密码、令牌、验证码及其摘要不进入前后值。敏感凭据发生变化时可以留下字段名，从而知道发生过变更，但无法从历史恢复凭据。技术限流、幂等和模拟调度表不做全行版本复制。

历史表拒绝普通 UPDATE、DELETE 和 TRUNCATE；它是追加记录，但数据库拥有者或超级用户可以主动改变结构，因此不是防数据库管理员篡改的证据系统。

升级只为现存业务记录建立当前状态 BASELINE，原有订单、账户和库存保持原值。此前没有记录下来的旧值无法恢复，完整的行变更历史从本次升级后开始积累。原有库存流水、物流节点、消息及操作审计仍然保留，可以与新历史一起查询。此功能不等于数据库备份。

0007/0008扩展使用说明见[商品购物与平台运营](commerce/shopping-and-platform.md)。查看图片元数据用 `--rows commerce_product_images`，查看图片变更用 `--history commerce_product_images`；图片内容不会显示在普通查询或历史快照中。
