# 第三步实现切片

日期：2026-10-06。用户授权实际开发第三步；commerce-v1仍是业务依据。
本文记录实现边界，完成状态以对应验证记录及PR为准，不以此文代替运行证据。

## 交付范围

实现独立商城身份/会话，商品/SKU/库存、Cart、跨店Checkout/Order、模拟PaymentAttempt、
取消/过期、地址revision、分包Shipment/Tracking、客户确认收货，以及双端/演示控制台。
迁移为新增0003，既有0001/0002和客服模块保持兼容。DEMO结果端点仅development/test。

消息/会话、售后/退款、真实支付/承运商、AI及经营上线不在此切片。
订单after_sale_cases暂时返回空列表；不把空列表声明为售后流程已实现。

## 初版并发实现选择

在冻结的权限、版本和库存规则之上，Commerce写入额外使用按数据库schema隔离的
PostgreSQL事务级advisory互斥锁，并继续锁定当前身份/对象。所有Commerce业务写入
采用一致入口，锁等待有界；等待过长返回OPERATION_BUSY，由界面保留原key重试。
不通过悄悄重复写入绕过锁冲突；事务回滚自动释放锁。

这一选择将同schema写请求串行化，便于当前低吞吐演示保证库存/金额/跨店下单原子性。
它不是高吞吐商城方案，也不能替代状态/对象版本/权限检查或唯一约束。后续需要更高
并发时必须单独设计细粒度锁并重跑独立连接并发测试，不在本次提前加复杂基础设施。

## 操作边界

客户发起付款尝试，DEMO控制台模拟支付回调，商家发货，DEMO模拟物流，客户确认收货。
前端所有事实读取来自平台API，Bearer只存内存；刷新需重新登录但业务持久化。
Seed只在development/test且显式密码配置下执行，不覆盖账号、价格、库存或历史状态。

## 开发中契约补充

CartLineView新增product_title、shop_name、options（当前公开商品/店铺信息），与SKU ID一并
返回；用于购物车显示用户能认出的商品，避免把内部UUID作为商品名称。下架后仍可显示
所选商品及purchasable=false。订单仍使用购买快照，不把购物车当前描述当历史快照。
Cart字段先记录契约，再同步前后端与验收；不新增业务模块或放宽权限。
商家SKU视图另显式返回version，用于已冻结SKU编辑的expected_version；公共SKU不增加此字段。
MerchantProductView/ MerchantSKUView按权限分别序列化，避免要求用户猜测编辑版本。

## 已注册接口清单

以下36项仅指第三步 development/test；前缀 /api/commerce/v1。
production不注册最后四项DEMO接口。完整设计表中的其他消息、Case、退货/退款端点尚不存在。

| 组 | 实现端点 |
| --- | --- |
| 身份（3） | POST auth/login；GET auth/me；POST auth/logout |
| 公共商品（2） | GET catalog/products；GET catalog/products/{product} |
| 商家商品/库存（11） | GET merchant/shops；GET/POST merchant/shops/{shop}/products；GET products/{product}；POST products/{product}/edit、publish、archive、skus；POST products/{product}/skus/{sku}/edit；GET inventory/{sku}；POST inventory/{sku}/adjust（商品/库存路径均属于merchant/shops/{shop}） |
| 客户购买（11） | GET customer/cart；POST customer/cart/lines；DELETE customer/cart/lines/{sku}；POST customer/checkouts；GET customer/checkouts/{checkout}；GET customer/orders；GET customer/orders/{order}；POST customer/orders/{order}/address、cancel、payments、confirm-receipt |
| 履约读取/发货（5） | GET merchant/shops/{shop}/orders；GET merchant/shops/{shop}/orders/{order}；POST merchant/shops/{shop}/orders/{order}/shipments；GET customer/orders/{order}/shipments/{shipment}；GET merchant/shops/{shop}/orders/{order}/shipments/{shipment} |
| DEMO（4） | GET demo/pending；POST demo/payments/{attempt}/result；POST demo/shipments/{shipment}/events；POST demo/orders/expire |

成功响应使用闭合Pydantic DTO并在提交前验证。接口输入仍先进行身份/对象授权，再解释
闭合JSON；因此OpenAPI说明不替代运行时校验。命名空间与旧客服Bearer、角色、对象完全分离。
