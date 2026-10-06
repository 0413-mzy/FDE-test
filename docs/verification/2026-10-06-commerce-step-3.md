# 第三步购买与履约验证

日期：2026-10-06（Asia/Kuala_Lumpur）。授权：“开始第三部”。
起点89b988e；分支codex/commerce-purchase-fulfillment；计划提交be41547。
状态：购买/履约实现与本地技术验收通过；GitHub准确head CI见下方发布记录。
不是main合并、人工开发者批准、生产上线或整个54项业务矩阵完成。

## 实际产出

新增0003迁移及22张独立商城表、36个development/test端点（production32个）、
显式虚构Seed、用户/商家/DEMO页面。页面读取同一PostgreSQL中的交易事实。
范围见[第三步切片](../commerce/step-3-implementation.md)，启动见[development](../development.md)。
消息、售后Case、退款/退货、AI、真实支付/承运商未实现；after_sale_cases=[]。
既有0001/0002、客服身份/Inquiry/Providers/CaseContext保留兼容。

## 环境与执行命令

- 全新PostgreSQL17临时集群，Unix socket，listen_addresses为空，无系统服务注册。
  pytest每项使用独立fde_test_<uuid> schema，结束只清理自己的schema。
  浏览器每轮使用新建commerce_runtime_<uuid>，不清空或改写已有库。
- 独立Sandbox版本4131f1c4be7af6a6981e15379214d238228e8fa2，本次新建SQLite路径，
  127.0.0.1:19007；Product只经HTTP访问，无Sandbox import或数据库读取。
- Product127.0.0.1:18008、Vite127.0.0.1:5179；精确配置对应CORS与VITE_API_BASE_URL。
  SystemClock用于页面；数据库边界测试注入固定UTC时钟并显式推进。
- 已安装Chrome+bundled Playwright，独立临时profile；不读取用户浏览器资料。
  Seed密码随机生成，0600本机文件，运行时读取；不写入Git、截图或日志。

在backend目录，显式TEST_DATABASE_URL为本次隔离集群：

```sh
python -m pytest -q -p no:cacheprovider --sandbox-url http://127.0.0.1:19007
ruff check .
ruff format --check .
```

在frontend目录：`npm test`、`npm run lint`、`npm run build`（内含typecheck）。
仓库根目录：`node --check scripts/commerce-browser-acceptance.cjs`、`git diff --check`。
完整浏览器脚本的配置/新Seed前提见[可选验收说明](../development.md#可选真实浏览器验收)。

## 最终观察结果

| 检查 | 结果 |
| --- | --- |
| 完整后端回归 | **358 passed，0 failed，0 skipped，123.30s**；1个既有Starlette弃用警告 |
| 新商城用例 | 41个（含参数化边界）；已纳入完整358，不重复加到总数 |
| 前端client/请求状态测试 | **10 passed，0 failed，0 skipped** |
| Ruff lint / format | 通过；62文件格式检查通过 |
| ESLint / TypeScript / Vite build | 通过；真实API构建，无业务mock回退 |
| 本机真实Product HTTP | 重启后两单COMPLETED持久化、跨客户404、401/403、分页、no-store、Origin边界、退出撤销通过 |
| 完整Chrome双端脚本 | 两店两单、两次成功付款、三包裹含分批发货、三次送达、两单收货通过；0 page errors |
| Chrome丢响应测试 | 已提交库存+2后丢弃响应；导航/刷新后新的版本请求被阻止；原body/key重放不再次+2；0 page errors |
| 手机390px页面 | 商品页无横向溢出；刷新清除内存会话；截图已保存 |
| 文档链接 / whitespace / 脚本语法 | 通过；发布前再次核对 |
| 本机Compose启动 | **NOT_RUN**：Docker CLI/Desktop不可用；不安装系统软件，配置由GitHub CI验证 |

## commerce-v1场景证据映射

下表是第三步已执行子项的映射，不把一个测试数冒充54项全部完成。
凡跨③④的场景，仅③部分有证据；第四步部分均NOT_RUN。
主要自动化文件：[test_commerce.py](../../backend/tests/database/test_commerce.py)。

| 场景 | 本次证据 / 范围 |
| --- | --- |
| C01 | owner_product_sku_inventory_and_nested_ownership：草稿、新SKU、上架、公开可见性；浏览器读取实际catalog |
| C02–C05 | split_payment_partial_ship_deliver_receipt +完整Chrome脚本：拆店金额、扣预留、两包分批、全部送达后收货；tracking测试含单包运输/送达 |
| C06 | price_confirmation_inventory_guard_and_order_snapshot：标题/价格修改不重写购买快照 |
| C07 | 真实HTTP重启后读取、浏览器独立会话/重新登录与刷新会话清除；seed_preserves_business_password_and_member_changes |
| C08–C09 | payment_failure_retry_snapshot_and_event_replay；shop_payment_results_are_independent |
| C10–C11 | permissions_before_validation_and_replay中的未付取消；address_revision_and_shipping_prestate |
| P01–P04 | permissions_before_validation_and_replay、invalid_merchant_path_does_not_disclose_before_identity、owner_product_sku_inventory_and_nested_ownership、真实HTTP跨客户检查；旧客服和新商城分别使用不同会话表 |
| P05–P07 | membership_revocation_precedes_shipment_replay、combined_capabilities_suspended_new_purchase_existing_fulfillment；只验证③权限/履约 |
| P08–P10 | atomic_stock_price_and_closed_inputs、price_confirmation_inventory_guard_and_order_snapshot；JSON/参数重复、伪造字段、bool数量、缺货、价格确认与库存守恒 |
| P11–P12 | split_payment_partial_ship_deliver_receipt、address_revision_and_shipping_prestate、shipment_rejects_excess_and_foreign_lines_then_replays_original |
| P19–P20 | production_no_demo_routes_and_closed_unknown_errors、authority_revoked_while_waiting_is_refreshed_before_write、actor_row_lock_bounds_business_and_failure_audit |
| R01–R02 | 原checkout/DELETE/发货HTTP响应重放、同key异body、同事件换HTTP key；另有initial事件ID冲突409；④重放未执行 |
| R03–R05 | last_item_real_concurrent_connections、same_checkout_key_concurrency_original_snapshot、pay_cancel_and_ship_concurrency_preserve_inventory、two_distinct_success_callbacks_consume_inventory_once；均独立线程/PG连接 |
| R06–R08 | payment_expiry_exact_boundary（899/900/901）、checkout_expiry_releases_entire_old_multiline_order、cancel_expired_stale_version_commits410_and_replays、atomic_stock_price_and_closed_inputs及checkout Audit故障回滚 |
| R09–R10 | 发货余量竞争；tracking_recovery_time_and_terminal_guards：异常恢复、倒序/未来拒绝、终态不反转与事件重放 |
| R14–R15 | audit_failure_rolls_back_payment_shipment_tracking及checkout故障：状态/库存/事件/key同事务回滚；expiry_inventory_adjustment_real_concurrency：释放与减库存竞争 |
| C12–C19、P13–P18、R11–R13 | **NOT_RUN / NOT_IMPLEMENTED**：消息、售后、退货与退款属于第四步 |

没有对每个商品/SKU编辑控件分别录制完整浏览器脚本；它们已接实际API，后端规则和
前端类型/构建已验证。完整业务场景演示及更广压力测试留第五步，不宣称绝大多数真实经营
场景已覆盖。现有③自动化及完整双端流程不以这一限制代替金额/库存/权限检查。

## 审查和修复

独立代理做前后端契约审查，再做质量/安全审查；root复核并执行最终检查。
这属于自动化辅助审查，不等于外部开发者批准或授权合并main。

已修复：严格RFC3339、商家先认证再解析ID、初始物流event_id冲突、64KiB有界流读取、
等待锁后重新检查权限、未知失败/BUSY的脱敏独立审计，以及审计本身的有界锁等待。
前端跨视图保留原始请求/key，阻止未确认写入后的新操作；订单金额标签、地址输入上限对齐。
每个行为修复有相关回归；审查无剩余阻断项。

## 截图与限制

[商品页](commerce-step-3/catalog.png) · [商家分批发货](commerce-step-3/merchant.png) ·
[客户完成订单](commerce-step-3/completed.png) · [手机商品页](commerce-step-3/mobile.png)。
商品为本地CSS示意插画，明确非实物照片。记录和地址全部虚构，支付和配送明确模拟。

同schema写入串行化，业务锁等待2s；失败审计另有2s锁/2.5s语句超时，无法写入审计时
保留安全主错误，不谎称审计落库。这是低吞吐MVP，不是生产高并发设计。
HTTPS、登录滥用防护、生产部署/真实支付评审尚未完成；容器实际构建/启动未验证。

## GitHub发布记录

实现提交：`da82e61217d75337f4d597ae6c1433df44a7414b`。已发布并附加到本任务的
[Draft PR #4](https://github.com/0413-mzy/FDE-test/pull/4)，base为codex/commerce-domain-contracts，
依赖[第二步PR #3](https://github.com/0413-mzy/FDE-test/pull/3)，不合并main。
[实现提交CI](https://github.com/0413-mzy/FDE-test/actions/runs/37476818231)包含backend、frontend、
database、compose；文档追记会产生新head，最终状态以PR当前head检查为准，不用历史CI冒充。
仓库简介已同步到“购买与履约候选实现见Draft PR #4”，未把候选分支说成main。

本次商城API、Vite和临时PostgreSQL保留运行供本机查看；独立Sandbox验收后已停止。
这不是系统服务或生产部署，重启/换环境按development重新配置自己的开发库。
