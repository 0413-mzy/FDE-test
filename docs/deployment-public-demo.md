# 公开演示部署与恢复

日期：2026-10-07。这是虚构业务演示，支付、物流、退款均模拟，无真实资金流转。
当前公开服务分支：`codex/commerce-conversation-ai`，继承 `codex/commerce-public-demo-deployment`，不合并 main。
云端上线状态与验证见[本次记录](verification/2026-10-07-public-demo.md)。

## 服务与费用

一个 Render Docker Web Service 同源提供静态前端与 FastAPI；一个独立 Neon Free
PostgreSQL 保存云端业务。使用 Virginia / AWS us-east-1，保持数据库和服务邻近。
用户随后选择暂不创建付费服务，并确认采用 Render Free + Neon Free；Render 创建页
显示每月0美元。保持单实例，不添加支付方式、付费数据库、域名或第二个服务。
闲置15分钟会休眠，唤醒通常约1分钟。没有支付方式时，超出免费带宽会暂停服务，
构建分钟耗尽会停止新构建；不自动升级为付费服务。额度请在 Billing 检查。
Neon Free 的额度用尽可能暂停；不是无限容量或正式经营的可用性保证。

参考：[Render 免费限制](https://render.com/docs/free)、[Render Blueprint](https://render.com/docs/blueprint-spec)、
[Render 价格](https://render.com/pricing)、
[Neon Free 当前额度](https://neon.com/blog/neon-free-plan-1-gb-per-project)。

## 精确部署配置

使用[Dockerfile](../deployment/Dockerfile)与[Blueprint](../render.yaml)。手动创建时：

- 仓库 `https://github.com/0413-mzy/FDE-test`，选择上述候选分支，Root Directory 留空。
- Dockerfile Path `deployment/Dockerfile`，Region Virginia，单实例，Health Check `/ready`。
- 关闭自动部署，每次明确部署已验证的 commit。
- `APP_ENV=production`；`COMMERCE_PUBLIC_DEMO=true`；`COMMERCE_PUBLIC_DEMO_BOOTSTRAP=true`。
- `DATABASE_URL`：新建独立 Neon 演示库的 **direct/unpooled** 连接，保留 TLS 参数；
  不能填写本机现有数据库，也不能使用 Neon pooled 地址，因为初始化使用会话锁。
- `COMMERCE_DEMO_PASSWORD`：独立随机值，至少12字符；页面会刻意公开此访客密码。
- `COMMERCE_OPERATOR_PASSWORD`：另一个随机值，至少20字符，绝不公开。
- Render 自动注入 `RENDER_EXTERNAL_URL` 作为 HTTPS 公共源；自定义域名时设置
  `COMMERCE_PUBLIC_ORIGIN` 为实际 HTTPS 源。不要在云端设置本地验收开关。

服务以非 root 用户、单 worker 启动，先执行增量迁移，再显式初始化新的虚构账号。
空业务库只初始化一次；以后验证既有账号与配置相符，不覆盖订单、图片、库存或审核状态。
`/ready` 同时检查数据库与迁移版本；不会仅因网页可打开便视为数据库可用。

公开账号为 customer.a / customer.b / owner.a / owner.b / staff.a / demo / dual.a。
platform / reviewer 使用私密管理密码，不列入公开页面。注册、邮箱验证/找回密码、
账号资料与密码修改、入驻申请写入在公开演示中关闭，地址和消息只填写虚构资料。
图片全库上限32MiB，请求体有限制；限流是单实例内存计数，重启后计数清空。

## 验证与更新

CI 的 `public-demo-container` 真实构建 Docker 镜像，连接隔离 PostgreSQL17，验证
静态资源、权限、图片、购买/付款/发货/收货，并重启同一容器验证数据保留。
Neon 当前项目使用 PostgreSQL18，云端仍须实际验证迁移与交易。

对新上线的演示 URL 运行：

```sh
python scripts/commerce-public-demo-acceptance.py --base-url https://实际演示地址 --receipt-file /tmp/commerce-demo-receipt.json
```

该命令会创建虚构订单和图片，消耗1件 Fictional Product A 库存；收据文件权限0600，
不包含密码或令牌。重启服务后运行：

```sh
python scripts/commerce-public-demo-acceptance.py --receipt-file /tmp/commerce-demo-receipt.json --check-persisted
```

需要同时进行真实浏览器登录、购物、图片显示和模拟操作验收；不要通过反复初始化
或重置库来恢复库存。商家按业务规则补库存即可。

## 备份和故障恢复

在每次升级前，对**云端演示库**执行 `pg_dump` 自定义格式备份；连接凭据放在
权限0600的 PostgreSQL service/pass 文件，不能放命令参数、Git 或普通日志。
安装与云库匹配的 PostgreSQL18 客户端后，以配置的 `commerce_cloud_demo` service 执行：

```sh
umask 077
pg_dump --dbname='service=commerce_cloud_demo' --format=custom --file=commerce-demo.dump
pg_restore --list commerce-demo.dump
```

service 配置包含 host/dbname/user/sslmode=require，密码存放受保护的 passfile；
数据转储包含共享消息、地址、业务历史和密码哈希，也必须保持私密。
不要把原本机数据库作为备份目标，不依赖容器文件系统保存数据库或图片。
在另建的恢复测试库中恢复并检查订单、图片、历史，再考虑切换连接：

```sh
pg_restore --dbname='service=commerce_restore_test' --no-owner --no-acl commerce-demo.dump
```

恢复测试库必须为空且与运行库独立；上述命令不使用 `--clean` 或删除现有库。
Neon 的短期恢复窗口可辅助恢复，但不能代替独立备份和恢复验证。

代码回滚：在 Render 选择已验证的先前 commit 重新部署；保留当前数据库与凭据。
迁移只增量升级，不自动 downgrade/reset。若旧代码不兼容新迁移，应修复前进或先在
独立恢复库验证，不能删除业务表来迁就回滚。

启动失败时先确认 `/ready`、迁移版本、direct连接、TLS、正确分支和两类密码是否匹配。

## 会话AI候选部署

会话AI候选位于 `codex/commerce-conversation-ai`，依赖原公开部署分支。
升级仍使用现有免费服务和独立云库，增量0009不覆盖原业务行。
在Render后端私密环境配置 `DEEPSEEK_API_KEY`，可选 `DEEPSEEK_MODEL=deepseek-flash`，
并将部署分支改为已验证的AI候选后明确手动部署。API密钥不放入Git、前端环境或公开截图。
缺失密钥时商城继续运行，但商家AI不可用。分享页面仅展示共用虚构账号密码。

DeepSeek调用会产生独立的模型用量，与Render/Neon免费托管费用不同。
本轮用户对AI月预算不设固定金额上限；不升级网站资源、不添加支付方式。
仍保留请求范围、账户/全局频率与并发限制。公开演示的商家账号是共用账号，
摘要及会话也属于共享虚构业务，不应接收真实个人资料。
如果初始化在迁移/seed之间中断，服务会拒绝不完整或不明的非空库。保留库、导出备份，
诊断事务与账号完整性；修复配置或经单独审查的恢复操作，不强制覆盖既有账号/订单。
DeepSeek会话摘要与建议回复已接入公开演示；真实邮件、支付及承运商仍未接入。
