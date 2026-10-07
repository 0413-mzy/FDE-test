# API契约：commerce-v1

**第三步实现购买与履约端点；第四步实现消息、售后和模拟退款端点。**
实现边界见 [第三步切片](step-3-implementation.md)与[第四步切片](step-4-implementation.md)。命名空间 `/api/commerce/v1`（下表省略此前缀）；
旧 `/api/v1/auth`、Inquiry等接口继续按旧契约，不复用新Bearer或业务对象。
详细状态/数量规则见 [lifecycle](lifecycle.md)，对象访问见 [permissions](permissions.md)。

## 1. 通用请求与结果

- JSON闭合对象，拒绝未知字段、重复JSON键、重复查询键/重复Idempotency-Key；禁止bool冒充整数。
- 身份与对象授权优先：无会话401；缺能力403；无权对象/未知对象404；合法对象之后校验业务。
- UUID标准字符串；UTC时间RFC3339；枚举严格；字符串trim后校验；不得提交actor/role、
  任意order_status、金额合计、simulation或source字段以决定事实。
- 每个POST成功创建资源201；修改/状态动作200；DELETE成功204。登录200，退出204。
  无成功创建后的异步202承诺。具有单项GET的资源创建响应带Location（不含令牌）；其他创建返回ID并由父资源/列表读取。
  错误带安全request_id。
- 写入既有聚合需要body `expected_version`（正整数），具体聚合见表；新资源无版本时不要求。
  没有通用PATCH状态接口。GET不写库，不触发取数或付款；列表用limit默认20，1..100，
  offset默认0，≥0，稳定created_at DESC/id DESC；Message/Tracking时间线例外为ASC。
- 业务响应`Cache-Control: no-store`，CORS仅配置可信origin，暴露Location/X-Request-Id。
  登录字段不进日志；不记录Bearer、地址、消息原文或原始body。

### 幂等

除登录/退出外，每个写端点要求一个1..200字符可见ASCII（!至~，无空格/控制字符）的`Idempotency-Key`。作用域
(actor_id, operation, key)，operation含端点操作和聚合ID；规范化body（含expected_version）
摘要相同才是同一请求。成功响应快照/资源ID与领域变更同事务提交（IdempotencyRecord.response_payload）。
业务快照仅在授权数据库保留，不放入普通日志；登录令牌不进入该记录。

先验证当前身份/对象权，再查重放；已成功的相同body即使版本已增长也返回原成功结果
（200和`Idempotent-Replay: true`；DELETE重放仍204），不重复发货/扣库存/发送消息。
返回原操作快照和resource_ids，可能已非当前；UI重放后GET最新详情。新会员/所有权不让
其他actor重放你的结果。相同key不同body→409 IDEMPOTENCY_CONFLICT。

同key并发事务等待唯一记录/锁，后一请求重放已提交结果；等待超时返回409 OPERATION_BUSY，
没有已开始运行记录的202模型。不保存未提交的半成功结果。普通失败不记成功key，客户端修正
body应换新key；日志/Audit记录安全拒绝。ORDER_EXPIRED为已提交到期结果，保存幂等结果，
后续重放该key仍410，不复活库存。授权失效的重放仍401/403/404。

### 错误闭合结构

```json
{"error":{"code":"STOCK_UNAVAILABLE","message":"可售库存不足","request_id":"uuid","details":{"sku_id":"uuid","available":0}}}
```

details仅限本次调用有权读取的字段；无额外字段时`details={}`。公共catalog或自己的Cart可
披露目标SKU当前公开价格/可售数量，不披露其他客户/店铺对象或SQL。未知内部失败500固定
INTERNAL_ERROR，不能回显输入或数据库连接。业务错误码：

| HTTP | code | 语义 |
| --- | --- | --- |
| 400 | INVALID_REQUEST / IDEMPOTENCY_KEY_REQUIRED | 格式、未知字段、值域或缺key |
| 401 | UNAUTHENTICATED / INVALID_CREDENTIALS | 无有效会话或登录失败 |
| 403 | CAPABILITY_REQUIRED | 没有端点所需客户/店铺/演示能力 |
| 404 | NOT_FOUND | 对象不存在或无权读取，响应一致 |
| 409 | VERSION_CONFLICT / IDEMPOTENCY_CONFLICT / OPERATION_BUSY | 版本、重复键或锁等待冲突 |
| 409 | PRICE_CHANGED / STOCK_UNAVAILABLE / NOT_PURCHASABLE | 价格、数量或商品/店铺不可购买 |
| 409 | INVALID_STATE / QUANTITY_CONFLICT / ACTIVE_CASE_EXISTS | 前态、发货/退款数量或售后冲突 |
| 409 | RETURN_WINDOW_EXPIRED / INVALID_EVENT_ORDER | 退货窗口或物流事件时间/状态错误 |
| 410 | ORDER_EXPIRED | 到期结算已提交，付款/取消请求不再按未到期处理 |

版本增长：Cart行改动/成功checkout增长Cart.version；SKU编辑增长SKU.version，价格变动
额外增长price_version；Product编辑/发布/归档/新增SKU增长Product.version；库存变化增长
Inventory.version。任何订单关联状态/地址/尝试创建、包裹/事件或Case变更均增长Order.version，
同时增长实际变更的Attempt/Shipment/Case版本；纯读取、失败/幂等重放不增长。
追加Message不增长不可变Conversation.version。业务到期结算增长Order/Attempt/Inventory
实际改变的版本，即使响应410。checkout视图cart_version取持久化result_cart_version。

## 2. 类型与公共读视图

下列是实现的闭合DTO；字段全部必需，可null的字段明确标注。UUID/UTC/金额通用类型见上文。
实现不能把ORM对象全量序列化：

- **SessionView**：`token:string`（仅登录）、`expires_at:UTC`、`account:AccountView`。
  AccountView `{id,username,customer_enabled:bool,demo_enabled:bool,shops:MembershipView[]}`；
  MembershipView `{shop_id,shop_name,role:OWNER|STAFF,shop_status:ACTIVE|SUSPENDED}`，只列active成员关系。
- **SKUView**：`{id,sku_code,options:object<string,string>,unit_price_minor,currency:"CNY",price_version,
  active:bool,available:int}`。匿名不返回reserved、流水或购买者。
  商家本店 **MerchantSKUView** 额外返回`version:int`，用于SKU编辑的expected_version；
  公共SKUView不含此内部编辑版本。
- **ProductView**：`{id,shop_id,shop_name,title,description,status,version,skus:SKUView[]}`；公共仅PUBLISHED
  且店铺ACTIVE、只列active SKU；商家本店MerchantProductView使用MerchantSKUView，可看所有SKU。
- **InventoryView**：`{sku_id,on_hand,reserved,available,version}`，仅OWNER。
- **CartView**：`{id,version,lines:CartLineView[]}`；每行`{sku_id,shop_id,product_title,shop_name,options:object<string,string>,quantity,seen_price_version,
  seen_price_minor,current_price_version,current_price_minor,currency,available,purchasable:bool}`；
  商品停售仍显示旧选择与purchasable=false，不悄悄删除。总价由checkout按已确认价计算。
- **OrderLineView**：`{id,sku_id,title,options,unit_price_minor,quantity,shipped_qty,
  refunded_unshipped_qty,refunded_shipped_qty}`；title/options取购买快照。
- **OrderSummary**：`{id,shop_id,shop_name,status,financial_status,total_minor,currency,version,created_at,
  payment_deadline,payment_expired:bool}`。OrderView增加`{checkout_id,lines:OrderLineView[],
  address:AddressView,address_revision:int,shipments:ShipmentView[],payment_attempts:AttemptView[],
  after_sale_cases:CaseView[],completed_at:UTC|null,cancel_reason_code:string|null,cancelled_at:UTC|null}`；商家视图checkout_id为null，客户可读自己的ID。
- **AddressView**：`{recipient_name,phone,country_code:"CN",region,city,postal_code,address_line}`，限制见domain。
- **AttemptView**：`{id,state:PENDING|SUCCEEDED|FAILED,version,amount_minor,currency,simulation:true,
  created_at,finished_at:UTC|null,failure_code:string|null}`。状态取当前事实，支付失败与退款失败分开。
- **ShipmentView**：`{id,order_id,tracking_number,status,version,simulation:true,shipped_at,
  delivered_at:UTC|null,lines:[{order_line_id,quantity}],events:EventView[]}`；EventView
  `{id,event_id,kind,description,occurred_at,sequence:int,source:"SIMULATED_CARRIER"}`。
- **CaseView**：`{id,order_id,type,state,version,reason,requested_amount_minor,currency,created_at,
  lines:[{order_line_id,quantity}],decision_reason:string|null,return_shipment:ReturnView|null,
  refund_attempts:AttemptView[]}`；ReturnView `{tracking_number,state:IN_TRANSIT|RECEIVED,restock:bool|null,
  registered_at,received_at:UTC|null}`。尚未收货的restock=null。
- **ConversationView**：`{id,shop_id,customer_id,order_id:UUID|null,version,created_at}`；MessageView
  `{id,conversation_id,sender_side:CUSTOMER|MERCHANT,body,created_at}`，不公开其他账号资料。
- **Page<T>**：`{items:T[],limit,offset,has_more:bool}`；不隐含全库total；空列表成功200。
- **DemoItem**：`{id,kind:PAYMENT|REFUND|SHIPMENT,state,version,simulation:true,created_at}`，
  不含客户、金额、地址或订单内容。demo队列只列PENDING付款/退款及未DELIVERED Shipment。

`has_more`按本授权结果limit+1计算。SKU价格/库存停用后，历史订单详情仍显示原快照。
各DTO由专用授权视图生成，不全量序列化ORM或暴露内部账号字段。

第四步增量字段：当前订单读取和新写入快照包含 `shop_name`，来自已授权订单的店铺。
第三步已存的幂等响应仍原样重放，可能不含该字段；不回填或改写历史快照。
客户端在重放后 GET 最新订单，用当前授权读取显示店铺名称。

## 3. 身份、商品与购物车

表中body必须恰好由列出的字段组成。`address`同AddressView；`options`最多10键，每键/值1..80。
`username`匹配小写ASCII `[a-z0-9_.-]{1,80}`、password12..128；title1..200、description0..5000；sku_code1..80。
每Product最多50个SKU（包含inactive记录）；同Product的SKU options组合唯一。初版新建Product带一个SKU，
其余通过SKU端点新增；不接受图片上传，页面使用本地占位图。

| 端点 | 权限/请求 | 成功结果 |
| --- | --- | --- |
| POST /auth/login | `{username,password}` | SessionView，200；不要求幂等key |
| GET /auth/me | 有效会话 | AccountView |
| POST /auth/logout | 有效会话、空body | 204；不要求幂等key |
| GET /catalog/products | 匿名；limit/offset；可选shop_id、q(1..100) | Page<ProductView>；搜索title/description，店铺筛选 |
| GET /catalog/products/{id} | 匿名 | ProductView |
| GET /merchant/shops | 店铺能力 | Page<MembershipView>，仅自身active成员关系 |
| GET /merchant/shops/{shop}/products | OWNER；limit/offset | Page<ProductView> |
| GET /merchant/shops/{shop}/products/{id} | OWNER且本店 | ProductView，含MerchantSKUView |
| POST /merchant/shops/{shop}/products | OWNER；`{title,description,sku:{sku_code,options,unit_price_minor,initial_stock}}` | ProductView(DRAFT)，201；initial_stock0..1000000 |
| POST /merchant/shops/{shop}/products/{id}/edit | OWNER；`{expected_version,title,description}`，Product版本 | ProductView |
| POST /merchant/shops/{shop}/products/{id}/publish | OWNER；`{expected_version}`，Product版本 | ProductView(PUBLISHED) |
| POST /merchant/shops/{shop}/products/{id}/archive | OWNER；`{expected_version}`，Product版本 | ProductView(ARCHIVED) |
| POST /merchant/shops/{shop}/products/{id}/skus | OWNER；`{expected_version,sku_code,options,unit_price_minor,initial_stock}`，Product版本 | ProductView，201；新增SKU同时Product.version增加 |
| POST /merchant/shops/{shop}/products/{id}/skus/{sku}/edit | OWNER；`{expected_version,unit_price_minor,active}`，SKU版本 | SKUView，增加SKU.version；价格改变才增price_version |
| GET /merchant/shops/{shop}/inventory/{sku} | OWNER | InventoryView |
| POST /merchant/shops/{shop}/inventory/{sku}/adjust | OWNER；`{expected_version,delta,reason}`，Inventory版本；delta非零整数±1000000，reason1..200 | InventoryView，事务增加流水 |
| GET /customer/cart | CUSTOMER；首次客户Seed建立Cart | CartView |
| POST /customer/cart/lines | CUSTOMER；`{expected_version,sku_id,quantity,seen_price_version}`，Cart版本；设置绝对quantity不是追加 | CartView；新建行201、替换行200 |
| DELETE /customer/cart/lines/{sku} | CUSTOMER；JSON `{expected_version}`，Cart版本；前端请求保留body | 204；未知行404 |

SKUView用于公开售卖视图；商家SKU edit结果增加`version:int`（MerchantSKUView），
商家ProductView的skus为MerchantSKUView以支持后续编辑。公开Product版本不授予写权限。
所有从属{shop}/{id}/{sku}都必须匹配，不允许把其他店的SKU放在本店路径绕过验证。
GET /merchant/shops同样接受limit/offset。q不接受SQL片段语义，只作长度限定的文本搜索。

## 4. 订单、支付与履约

| 端点 | 权限/body及expected_version对象 | 成功结果 |
| --- | --- | --- |
| POST /customer/checkouts | CUSTOMER；`{expected_version,address}`，Cart版本；非空Cart | `{id,order_ids:UUID[],orders:OrderSummary[],cart_version}`，201 |
| GET /customer/checkouts/{id} | 本客户 | `{id,order_ids:UUID[],orders:OrderSummary[],cart_version}`；cart_version是提交后的版本 |
| GET /customer/orders | 本客户；limit/offset，可选status精确枚举 | Page<OrderSummary> |
| GET /customer/orders/{id} | 本客户 | OrderView |
| POST /customer/orders/{id}/address | 本客户；`{expected_version,address}`，Order版本 | OrderView |
| POST /customer/orders/{id}/cancel | 本客户未付；`{expected_version,reason}`，Order版本，reason1..500 | OrderView(CANCELLED)；到期返回410并结算 |
| POST /customer/orders/{id}/payments | 本客户；`{expected_version}`，Order版本 | AttemptView(PENDING)，201；同时Order.version增加 |
| POST /customer/orders/{id}/confirm-receipt | 本客户；`{expected_version}`，Order版本 | OrderView(COMPLETED) |
| GET /merchant/shops/{shop}/orders | active成员；limit/offset，可选status | Page<OrderSummary>，只本店 |
| GET /merchant/shops/{shop}/orders/{id} | active成员且本店 | 商家OrderView |
| POST /merchant/shops/{shop}/orders/{id}/shipments | active成员；`{expected_version,lines:[{order_line_id,quantity}]}`，Order版本 | ShipmentView，201；1..50行、去重ID、数量1..99 |
| GET /customer/orders/{id}/shipments/{shipment} | 本客户、本订单 | ShipmentView |
| GET /merchant/shops/{shop}/orders/{id}/shipments/{shipment} | active成员、本店、本订单 | ShipmentView |

checkouts不接受client_total、shop_id或actor_id；店铺来自Cart SKU关联；清空Cart与所有拆单
在一个事务内。付款和退款展示simulation=true，每店支付独立；Order详情每次重新计算
payment_expired，不把旧deadline伪装成可付款。公共消息和物流不会自动发起付款/退款。

## 5. 消息与售后（第四步实现）

| 端点 | 权限/body及expected_version对象 | 成功结果 |
| --- | --- | --- |
| POST /customer/conversations | CUSTOMER；`{shop_id,order_id:UUID|null}` | ConversationView，首次201；已存在200，不重复建会话 |
| GET /customer/conversations | 本客户；limit/offset | Page<ConversationView> |
| GET /merchant/shops/{shop}/conversations | active成员；limit/offset | Page<ConversationView> |
| GET /customer/conversations/{id}/messages | 本客户；limit/offset，created_at/id ASC | Page<MessageView> |
| GET /merchant/shops/{shop}/conversations/{id}/messages | active成员、本店；limit/offset，ASC | Page<MessageView> |
| POST /customer/conversations/{id}/messages | 本客户；`{body}`，无expected_version，追加幂等 | MessageView，201 |
| POST /merchant/shops/{shop}/conversations/{id}/messages | active成员、本店；`{body}`，无expected_version | MessageView，201 |
| POST /customer/orders/{id}/after-sales | 本客户；`{expected_version,type,reason,lines:[{order_line_id,quantity}]}`，Order版本；reason1..500 | CaseView(REQUESTED)，201；1..50行、去重ID |
| GET /customer/orders/{id}/after-sales/{case} | 本客户、本单 | CaseView |
| GET /merchant/shops/{shop}/orders/{id}/after-sales/{case} | active成员、本店、本单 | CaseView；STAFF只读 |
| POST /customer/orders/{id}/after-sales/{case}/withdraw | 本客户；`{expected_version}`，Case版本 | CaseView(CANCELLED) |
| POST /customer/orders/{id}/after-sales/{case}/return | 本客户；`{expected_version,tracking_number}`，Case版本，运单1..100 | CaseView(RETURN_IN_TRANSIT)；明确模拟退货 |
| POST /merchant/shops/{shop}/orders/{id}/after-sales/{case}/decision | OWNER；`{expected_version,decision:APPROVE|REJECT,reason}`，Case版本；reason1..500 | CaseView，按类型进入下一态 |
| POST /merchant/shops/{shop}/orders/{id}/after-sales/{case}/receive-return | OWNER；`{expected_version,restock:bool}`，Case版本 | CaseView(REFUND_PENDING)，收到所有申请数量 |
| POST /merchant/shops/{shop}/orders/{id}/after-sales/{case}/refunds | OWNER；`{expected_version}`，Case版本 | AttemptView(PENDING)，201 |

通用会话只在Shop ACTIVE时新建；绑定本人已有Order可在Shop SUSPENDED时建会话，已存在
会话仍可沟通。消息不增加Conversation.version以免并发追加制造无意义版本冲突；
Conversation身份/绑定不可变；不实现消息删除、编辑、附件、已读回执或实时推送。
客户/商家通过刷新读取，退出或切换账号后不复用另一账号的消息缓存。

## 6. 窄演示接口

只在APP_ENV development/test且DEMO账号有效时启用；其他环境不注册路由。
支持显式筛选kind，可列需要处理的脱敏DemoItem；不是万能后台。

| 端点 | body | 结果 |
| --- | --- | --- |
| GET /demo/pending | limit/offset，可选kind | Page<DemoItem> |
| POST /demo/payments/{attempt}/result | `{expected_version,result:SUCCEEDED|FAILED,event_id}`，Attempt版本；event_id1..100 | `{id,state,version,simulation:true}`，无订单/金额；失败code固定SIMULATED_DECLINE |
| POST /demo/refunds/{attempt}/result | 同上，退款Attempt版本 | 同脱敏结果；失败code固定SIMULATED_REFUND_FAILURE |
| POST /demo/shipments/{shipment}/events | `{expected_version,event_id,kind,description,occurred_at}`，Shipment版本；description1..500 | `{id,status,version,simulation:true}`；kind IN_TRANSIT/DELIVERED/EXCEPTION |
| POST /demo/orders/expire | `{order_ids:UUID[]}`，1..100个去重ID；只作用PENDING_PAYMENT到期订单 | `{expired_ids:UUID[],unchanged_ids:UUID[]}`，不存在或未到期均unchanged，不透露详情 |

event_id全局去重（支付/退款/物流含来源类型），已处理同payload结果可安全重放，
改业务payload→409 IDEMPOTENCY_CONFLICT；比较event_id的业务内容不包含HTTP key或
expected_version，物流时间规范化成UTC。当前授权→event重放检查优先于版本/终态拒绝；
同业务结果可返回原脱敏结果，即使当前version增加。即使换HTTP key也不得重复处理事件。
模拟结果在锁后检查当前聚合/Attempt状态与数量约束；不信任演示操作者的状态声明。
/demo/orders/expire处理目标Order的所有行，不修改未付款已取消/已付状态，也不提供全库清理。

## 7. 双端显示约定

用户：商城→商品→Cart→拆单付款→我的订单→包裹→联系店铺/售后。
演示环境提供独立DEMO控制台，用于处理已发起的付款/退款和模拟物流；
客户付款页面显示PENDING并刷新Order，不能让客户角色直接调用demo结果端点。
商家：仅本人店铺入口→商品/库存→订单处理→发货→会话/售后。
付款失败展示可重新尝试（仅未到期）；价格/库存冲突让用户核实并重新提交新key；版本冲突
重新GET，不能悄悄以新version重复动作。演示物流异常展示事实，不自动推断退款资格。
所有操作后GET最新授权视图；刷新重新登录仍看到持久化业务记录。
