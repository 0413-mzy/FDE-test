# 第五步：场景完善与可复现演示验收

日期：2026-10-07（Asia/Kuala_Lumpur）。用户明确要求先进行第五步，部署留到之后。
基于第四步457470a，分支codex/commerce-scenario-hardening。不合并main，不进入AI或真实经营。

## 具体产出

- scripts/commerce-demo.py：显式隔离PostgreSQL、每场景唯一schema、迁移/Seed、随机0600密码文件，自己的API/Vite/浏览器及finally清理；不清库、不改已有订单。
- interactive模式输出本机地址和受保护密码文件供人体验；all模式一条命令跑七个独立场景。
- 54项commerce-v1场景精确关联pytest节点、必要浏览器场景和执行结果，见[机器清单](../commerce/step-5-coverage.json)。
- 新增13个真实PG回归：账号停用/店铺暂停、终态原请求重放、强制并发退款、混合退款数量、多商品原子拒绝、旧客服有效会话隔离、其他权限及已付取消。
- 异常浏览器验证改价拒绝与明确确认、已购价格快照、失败付款重试、物流异常恢复及重新登录。
- 修复刷新购物袋/确认价格清空地址；草稿仅当前Cart内存，无浏览器持久化。修复刷新订单详情时列表仍旧状态。
- CI增加运行器安全测试与脚本Ruff；既有数据库回归继续运行，无冻结迁移/API变化。

## 本次实际验证

| 检查 | 实际结果 |
| --- | --- |
| 全部商城真实PostgreSQL回归 | **70 passed、0失败/跳过，100.39秒**，JUnit逐节点核对 |
| 非数据库/非integration后端回归 | **161 passed，223 deselected**，1.52秒 |
| 运行器安全回归 | **5通过**，生产/URL拒绝、随机凭证/schema、204空响应、中断覆盖旧报告且exit130 |
| 前端测试 | **13通过**，0失败/跳过 |
| 前端lint/typecheck/build | 通过 |
| Ruff | backend/scripts通过，69个Python文件格式通过 |
| 七个真实Chrome场景 | 全通过、每场景新schema；没有页面错误；详情刷新与列表一致断言通过 |
| 真实HTTP | 七场景均验证未登录cart/order401、重复query/JSON400且业务未变化 |
| API进程重启 | 七场景各重启一次，授权GET完整订单/支付/物流/售后前后完全一致 |
| 本机原演示服务 | 原进程已停止，本次使用原配置/schema恢复18008/5179；未Seed/重置/迁移原库 |
| Compose/全仓库数据库回归 | 本机没有Docker；准确提交GitHub CI为准 |

命令（backend目录，TEST_DATABASE_URL显式隔离集群）：

```sh
python -m pytest tests/database/test_commerce.py tests/database/test_commerce_step4.py tests/database/test_commerce_step5.py tests/database/test_commerce_step5_permissions.py -q -p no:cacheprovider --junitxml=/tmp/commerce-pytest.xml
python -m pytest -m 'not database and not integration' -q -p no:cacheprovider
```

根目录：`python -m unittest discover -s scripts/tests`、`ruff check backend scripts`、
`ruff format --check backend scripts`、`node --check scripts/commerce-step5-browser-acceptance.cjs`。
前端：`npm test`、`npm run lint`、`npm run build`（含typecheck）。

浏览器：显式APP_ENV/TEST_DATABASE_URL/PLAYWRIGHT_MODULE/CHROME_EXECUTABLE，
`python scripts/commerce-demo.py --scenario all --evidence-dir /tmp/commerce-evidence`。
[启动说明](../development.md#第五步统一演示入口)。固定时钟用于PG边界，SystemClock用于真实页面。
同schema写入仍串行；并发测试使用独立连接，R12在pg_locks观察实际等待而不是等待若干秒猜并发。

安全汇总证据：[70项节点结果](commerce-step-5/pytest-results.json)、
[七场景及源码标识](commerce-step-5/browser-results.json)、
[异常截图](commerce-step-5/exception.png)、[完成截图](commerce-step-5/completed.png)。
浏览器是在未提交工作树上执行，因此报告同时记录基线HEAD、dirty=true与实际源码树SHA256；
不把基线457470a说成包含第五步实现。提交后CI另行验证准确head，报告不含连接串/密码/令牌。

## 54项逐项结果

下面PASSED表示该commerce-v1场景的指定断言已经执行；不是54次独立浏览器录像、
所有真实电商业务覆盖、生产可用性或每个故障点×每个操作的全组合证明。
C02–C07、C12–C19均有本次独立浏览器场景对应证据；其余主要采用真实PostgreSQL规则/并发验证。

| ID | 状态 | 具体证据 |
| --- | --- | --- |
| C01 | PASSED | `test_owner_product_sku_inventory_and_nested_ownership`, `test_cart_delete_original_replay_and_catalog_controls` |
| C02 | PASSED | `test_split_payment_partial_ship_deliver_receipt`；浏览器 purchase |
| C03 | PASSED | `test_split_payment_partial_ship_deliver_receipt`；浏览器 purchase |
| C04 | PASSED | `test_tracking_recovery_time_and_terminal_guards`, `test_address_revision_and_shipping_prestate`；浏览器 return-no-restock |
| C05 | PASSED | `test_split_payment_partial_ship_deliver_receipt`；浏览器 purchase |
| C06 | PASSED | `test_price_confirmation_inventory_guard_and_order_snapshot`；浏览器 exceptions |
| C07 | PASSED | `test_commerce_persistent_purchase`；浏览器 purchase, exceptions |
| C08 | PASSED | `test_payment_failure_retry_snapshot_and_event_replay` |
| C09 | PASSED | `test_shop_payment_results_are_independent` |
| C10 | PASSED | `test_pay_cancel_and_ship_concurrency_preserve_inventory`, `test_unpaid_two_unit_cancel_and_paid_cancel_preserve_stock` |
| C11 | PASSED | `test_address_revision_and_shipping_prestate` |
| C12 | PASSED | `test_messages_and_partial_refund`；浏览器 partial-return |
| C13 | PASSED | `test_messages_and_partial_refund`；浏览器 partial-return |
| C14 | PASSED | `test_suspended_shop_existing_messages_and_refund_completion`；浏览器 full-refund |
| C15 | PASSED | `test_concurrent_case_requests_and_atomic_audit_failure`；浏览器 shipped-partial-refund |
| C16 | PASSED | `test_return_boundary_failure_retry_stock_and_events`；浏览器 partial-return |
| C17 | PASSED | `test_completed_partial_return_nonrestock_preserves_fulfillment_history`；浏览器 return-no-restock |
| C18 | PASSED | `test_overlapping_decisions_cannot_reopen_rejected_case`, `test_active_case_invalid_quantity_strict_body_and_exact_historical_replay`；浏览器 reject-withdraw |
| C19 | PASSED | `test_return_boundary_failure_retry_stock_and_events`；浏览器 partial-return |
| P01 | PASSED | `test_permissions_before_validation_and_replay`, `test_unauthenticated_and_foreign_namespace_token_cannot_read_cart_or_orders`, `test_valid_support_session_does_not_grant_commerce_access` |
| P02 | PASSED | `test_permissions_before_validation_and_replay`, `test_foreign_order_read_payment_cancel_and_shop_scope` |
| P03 | PASSED | `test_permissions_before_validation_and_replay`, `test_ownership_staff_suspended_and_auth_before_body`, `test_staff_price_and_demo_order_message_capabilities_denied` |
| P04 | PASSED | `test_owner_product_sku_inventory_and_nested_ownership` |
| P05 | PASSED | `test_membership_revocation_precedes_shipment_replay`, `test_ownership_staff_suspended_and_auth_before_body`, `test_account_deactivation_blocks_original_message_replay_and_reads` |
| P06 | PASSED | `test_combined_capabilities_suspended_new_purchase_existing_fulfillment` |
| P07 | PASSED | `test_combined_capabilities_suspended_new_purchase_existing_fulfillment`, `test_suspended_shop_existing_messages_and_refund_completion` |
| P08 | PASSED | `test_atomic_stock_price_and_closed_inputs`, `test_body_stream_limit_follows_authorization_before_parse_and_locks` |
| P09 | PASSED | `test_atomic_stock_price_and_closed_inputs`, `test_price_confirmation_inventory_guard_and_order_snapshot` |
| P10 | PASSED | `test_price_confirmation_inventory_guard_and_order_snapshot` |
| P11 | PASSED | `test_address_revision_and_shipping_prestate`, `test_split_payment_partial_ship_deliver_receipt`, `test_unpaid_two_unit_cancel_and_paid_cancel_preserve_stock` |
| P12 | PASSED | `test_shipment_rejects_excess_and_foreign_lines_then_replays_original` |
| P13 | PASSED | `test_active_case_invalid_quantity_strict_body_and_exact_historical_replay`, `test_active_case_nested_ownership_and_order_conversation_binding`, `test_mixed_shipped_unshipped_quantity_case_is_atomic`, `test_multiline_mixed_shipped_and_unshipped_case_is_atomic` |
| P14 | PASSED | `test_return_boundary_failure_retry_stock_and_events`, `test_return_all_parcels_window_and_registered_return_restrictions` |
| P15 | PASSED | `test_completed_partial_return_nonrestock_preserves_fulfillment_history`, `test_active_case_nested_ownership_and_order_conversation_binding` |
| P16 | PASSED | `test_return_all_parcels_window_and_registered_return_restrictions` |
| P17 | PASSED | `test_active_case_nested_ownership_and_order_conversation_binding`, `test_ownership_staff_suspended_and_auth_before_body` |
| P18 | PASSED | `test_ownership_staff_suspended_and_auth_before_body`；浏览器 partial-return |
| P19 | PASSED | `test_production_no_demo_routes_and_closed_unknown_errors`, `test_permissions_before_validation_and_replay`, `test_production_explicit_refund_callback_not_registered` |
| P20 | PASSED | `test_authority_revoked_while_waiting_is_refreshed_before_write`, `test_case_creation_overlaps_shipping_without_quantity_drift` |
| R01 | PASSED | `test_same_checkout_key_concurrency_original_snapshot`, `test_shipment_rejects_excess_and_foreign_lines_then_replays_original`, `test_payment_failure_retry_snapshot_and_event_replay` |
| R02 | PASSED | `test_payment_failure_retry_snapshot_and_event_replay`, `test_return_boundary_failure_retry_stock_and_events`, `test_finished_case_replays_original_decision_and_rejects_changed_body`, `test_refund_event_changed_result_conflicts_and_preserves_completed_order` |
| R03 | PASSED | `test_last_item_real_concurrent_connections` |
| R04 | PASSED | `test_same_checkout_key_concurrency_original_snapshot` |
| R05 | PASSED | `test_pay_cancel_and_ship_concurrency_preserve_inventory`, `test_two_distinct_success_callbacks_consume_inventory_once` |
| R06 | PASSED | `test_payment_expiry_exact_boundary[899-200]`, `test_payment_expiry_exact_boundary[900-410]`, `test_payment_expiry_exact_boundary[901-410]` |
| R07 | PASSED | `test_checkout_expiry_releases_entire_old_multiline_order` |
| R08 | PASSED | `test_atomic_stock_price_and_closed_inputs`, `test_mutation_failure_rolls_back_every_aggregate` |
| R09 | PASSED | `test_pay_cancel_and_ship_concurrency_preserve_inventory` |
| R10 | PASSED | `test_tracking_recovery_time_and_terminal_guards` |
| R11 | PASSED | `test_case_creation_overlaps_shipping_without_quantity_drift` |
| R12 | PASSED | `test_return_boundary_failure_retry_stock_and_events`, `test_distinct_refund_successes_forced_overlap_separate_connections` |
| R13 | PASSED | `test_finished_case_replays_original_decision_and_rejects_changed_body` |
| R14 | PASSED | `test_mutation_failure_rolls_back_every_aggregate`, `test_audit_failure_rolls_back_payment_shipment_tracking[demo.payment]`, `test_audit_failure_rolls_back_payment_shipment_tracking[merchant.ship]`, `test_audit_failure_rolls_back_payment_shipment_tracking[demo.tracking]`, `test_refund_success_rolls_back_every_business_record_then_retries[inventory]`, `test_refund_success_rolls_back_every_business_record_then_retries[order]`, `test_refund_success_rolls_back_every_business_record_then_retries[attempt]`, `test_refund_success_rolls_back_every_business_record_then_retries[event]`, `test_refund_success_rolls_back_every_business_record_then_retries[audit]` |
| R15 | PASSED | `test_expiry_inventory_adjustment_real_concurrency` |

## 审查、修复与限制

运行器首次RED发现204退出响应误解析，修复后安全测试/真实HTTP通过。
浏览器先观察到刷新丢地址和详情/列表不同步，添加断言先失败，再实现最小修复后七场景全通过。
独立代码审查发现HEAD不足以标识未提交源码、自动验收中断可能留下旧成功报告；已增加源码hash与
INTERRUPTED/nonzero及回归。审查复核无剩余重要缺陷，不等于外部人工开发者批准。

本次未重新执行35项integration标记测试（既有客服/Sandbox），未改该域源码；
当前387项collect结果不等于387项本次全跑。消息无推送/附件，物流及支付/退款均人工模拟。
R14退款覆盖库存/Order/Attempt/事件/Audit五处注入；其他操作用Audit失败验证整事务回滚，
没有宣称每个操作每个故障点全组合、性能负载或所有外部网络故障覆盖。
临时生成schema保留供调查，无自动删除，不影响用户原订单。重启操作系统后需按开发说明启动。
未部署公网、未合并main、未开始第六步AI。
