# 2026-10-07 商品体验与平台运营验收

本轮来自用户两张截图的明确功能请求，沿用此前全权执行授权。基于历史扩展最终提交3e082f0建立codex/commerce-catalog-platform-operations；依赖Draft PR #8，不部署、不合并main、不接AI或真实资金。实际规则见[领域说明](../commerce/shopping-and-platform.md)。

## 实现与验收范围

商品图片真实上传、解码并存库；分类、关键词/店铺/价格/库存过滤、排序、收藏、购买评价/修改及商家回复已接通界面和事务API。平台拥有独立资格、分类管理、账号/店铺/商品/评价处理、举报结案、可读处理记录、售后争议与双方证据、原售后事实查询、人工裁决及窄范围模拟退款入口。客户/商家/平台报表统计以成功模拟交易为准。

0007/0008添加九张业务表，并接入38张业务表的事务历史。冻结0006迁移与旧客服契约未重写。旧购买接口也检查限制，前端切换角色不能取得权限。原售后窗口与金额/数量规则继续适用。

独立规格审查与代码质量审查后，修复了未送达订单行可评价、畸形举报决定导致500、双角色证据归属、仲裁缺少原申请事实、报表无界明细和商家不可见商品限制状态。评价必须实际送达；平台审查显示购买/申请数量、金额和商家决定。争议期间发货、售后修改、地址修改及收货操作在后端冻结。未发现遗留P0/P1阻塞。

## 执行结果

- 真实PostgreSQL：`pytest tests/database -m 'not integration' -q`，229通过、11个外部integration取消选择、0跳过，197.75秒；最后补充争议地址/收货冻结断言后，平台10项再次通过（14.49秒）。
- 非数据库：在backend目录运行 `pytest -m 'not integration and not database'`，161通过、264取消选择。
- 脚本：`python -m unittest discover -s scripts/tests`，9通过。
- Python：`ruff check backend scripts` 和 `ruff format --check backend scripts` 通过，95文件格式一致。
- 前端最终：18测试通过；lint、typecheck、production build通过；新浏览器脚本语法及diff whitespace通过。
- 商品体验/平台运营真实Chrome独立场景通过：两店购买后图片分类筛选、收藏重载、评价回复、举报隐藏/恢复、店铺暂停保留旧单、客户争议与双方证据、平台裁决后模拟退款、金额统计与移动端零溢出/零页面异常。重启API后3张订单保持。证据 `/private/tmp/fde-shopping-platform-fifth-evidence/results.json`；工作树hash `f9c4b9a9b3ea747bf47bf95374bae323c1e8775aa8503cb36ce021e6da7d7f5e`，来源3e082f0且dirty=true，不能冒充已提交版本。

浏览器初次验收暴露分类控件定位与客户分类列表刷新问题，修正明确标签及刷新元数据；后续完善异步持久化断言等待后重跑通过。图片验收采用有效PNG而非不可靠fixture。界面业务写入经页面；额外未发货已付款订单前提由真实HTTP创建。

- 全部九个隔离浏览器场景：`python scripts/commerce-demo.py --scenario all` 通过，包括原购买、五种售后、异常恢复、入驻和新增商品/运营；各场景API重启后订单快照一致。证据 `/private/tmp/fde-shopping-platform-all-evidence/results.json`，同一工作树hash。

## 原本机数据库与服务

在受保护运行目录创建0600私有pg_dump备份 `pre-shopping-0008.dump`，先停止自己的API，再0006→0008升级。逐行对比47张旧数据表，迁移前后完全相同；显式平台seed后每一条旧记录仍相同，仅新增独立平台账号、资格及对应历史。共有57张表（包含迁移表）、38个业务历史触发器，历史没有图片content字节。

原本机API重启、原前端地址恢复。健康检查与114个commerce操作清单通过；customer.a、owner.a、owner.b、staff.a、demo、reviewer、platform七种身份的实际授权读取通过，原有订单/店铺名/售后记录保持。该检查仅登录/注销和业务读取，不产生新订单。原本机真实Chrome确认分类筛选及platform登录工作台，无页面异常。

网站仍为本机 http://127.0.0.1:5179/ ，API为本机18008端口。platform使用既有受保护演示密码文件配置；未把密码写入源码或文档。

## 交付限制

外部真实支付、承运商、真实邮件与AI未接入；Docker Compose由CI验证，本机无Docker。报表净额不是利润，不含成本/税费；平台仲裁围绕已有退款/退货申请，不是完整现实司法或支付争议系统。图片初版数据库BYTEA有界存储，未接云对象存储。没有公共部署或main合并。

## GitHub交付

实现提交 `cc37c6293659f76b42592f796c3aac65a8db55a5`；[Draft PR #9](https://github.com/0413-mzy/FDE-test/pull/9)依赖PR #8。最后文档提交的精确HEAD CI在交付前通过GitHub checks核验，结果附于PR；不将本地工作树证据冒充最终提交CI。
