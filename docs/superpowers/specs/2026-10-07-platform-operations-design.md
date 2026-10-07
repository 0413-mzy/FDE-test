# 平台运营设计

用户2026-10-07请求补全管理后台、违规处理、售后争议与仲裁、经营报表。沿用全权执行授权；真实资金/部署/AI后置。依赖商品体验0007；增量0008。

## 独立身份与记录

独立PlatformRole(account唯一、active)赋予平台权限，不沿用客服Admin，不因review_enabled或demo_enabled获得权限。显式platform种子只创建新虚构账户，不提权旧账号；禁止自我停用/自行授予权限。账户资格GET /platform/access供导航，后端每次授权，平台业务权限不由前端切换产生。

新增ModerationReport（举报人、PRODUCT/SHOP/REVIEW目标、理由、OPEN/RESOLVED/DISMISSED）、ModerationAction（平台处理人、目标、WARN/HIDE/RESTORE/SUSPEND等决定、理由）、Dispute（customer/order/case、申请理由、双方补充纯文本、OPEN/UPHELD/OVERTURNED/WITHDRAWN、决定理由/操作者）；安全历史覆盖所有新表，无密码/图片二进制。保持既有状态/数据，通过加表关联而不改旧约束。

后台分页浏览账户（不输出密码摘要）、店铺、商品、评价、举报、争议，分类创建/编辑停用；重要修改带expected_version及必填理由。举报人只看自己的举报，相关商家只看本店可处理的信息；不暴露无关个人资料。

## 违规

客户可举报公开商品/店铺/评价，不能自造目标或枚举私人草稿；相同未处理目标/客户只一个有效举报。平台可警告、隐藏商品（独立ProductExperience moderation标记，商家再发布不能绕过）、隐藏评价、暂停/恢复店铺、停用/恢复普通账户，处理记录和举报决定原子保存。平台账户自身及其他平台账户不走普通账户停用。原有订单快照保持；暂停店铺阻止新购买/上架，旧订单履约/售后和双方消息继续开放。普通报告结案不等于自动执行金额/库存修改。

## 争议与仲裁

客户可对自身REJECTED售后，或REQUESTED超过48小时未处理售后申请争议；同售后最多一个OPEN，正文/证据为纯文本（初版不提供任意附件）。双方在OPEN时补充理由，客户可撤回。平台不能裁自己作为客户或其有店铺成员身份的订单。

OPEN期间冻结受争议售后及该订单新的冲突售后/发货，防止裁决期间数量变化；正常查询/消息不受影响。无争议订单行为保持兼容。平台裁决UPHOLD（维持商家决定/驳回申请）或APPROVE（支持原售后所选商品数量和金额），必填理由、版本及幂等键。APPROVE必须再次核对未退款余额/数量、其他活动案件、已发货事实，按原申请时退货窗口是否合法判断，不强行改成已退款。

APPROVE对未发退款进入REFUND_PENDING，对已送达退货进入AWAITING_RETURN；后续原商家退货接收/回库/模拟退款继续；平台可对仲裁获准REFUND_PENDING案件发起同一受控模拟退款尝试，结果仍只由DEMO适配结算。不得自动回库未收实物、不得重复退款、不得改历史购买金额。裁决、售后状态恢复与历史同事务；不适用的旧案件返回解释性冲突。

## 报表

GET平台报表与OWNER本店报表，明确CNY整数分、模拟标识、UTC区间[start,end)（最长366天）及已选店铺。实际支付成功时间内的成功payment_attempt金额作为支付总额；成功refund_attempt时间内金额为退款总额；净额=支付总额−退款总额，不称利润/银行结算。订单创建数、完成数、未付/待发/运输/售后待处理为独立指标，区分区间流量与当前积压；销量用订单行实购数量及相应退货/退款数量展示，不重复按包裹累计。按日和按店聚合，列表分页或有界365日，merchant不能跨店读取平台报表。

## HTTP/UI 协定

/platform/access；/platform/accounts、/platform/shops、/platform/products、/platform/reviews、/platform/reports、/platform/disputes 分页GET。
/customer/reports GET/POST {target_type,target_id,reason}；/customer/disputes GET，/customer/orders/{order}/after-sales/{case}/dispute POST {expected_version,reason}；/customer/disputes/{id}/evidence POST {expected_version,body}；/customer/disputes/{id}/withdraw POST {expected_version}。
/merchant/shops/{shop}/disputes GET，/{id}/evidence POST {expected_version,body}。
/platform/reports/{id}/decision POST {expected_version,decision:DISMISS|RESOLVE,action:WARN|HIDE_PRODUCT|RESTORE_PRODUCT|HIDE_REVIEW|RESTORE_REVIEW|SUSPEND_SHOP|RESTORE_SHOP|SUSPEND_ACCOUNT|RESTORE_ACCOUNT|null,reason}。直接后台处理POST /platform/moderation {target_type,target_id,expected_version,action,reason}，返回Action。
/platform/disputes/{id}/decision POST {expected_version,decision:UPHOLD|APPROVE,reason}；/platform/disputes/{id}/refunds POST {expected_version}。
/platform/categories GET/POST，/{id}/edit POST {expected_version,name,active}（共享catalog Category）。
/platform/analytics?start=ISO&end=ISO&shop_id=optional；/merchant/shops/{shop}/analytics同格式。

前端独立平台运营导航：总览/报表、账户/店铺/商品、分类、举报/违规、争议。客户/商家各有争议与举报状态入口，售后案件有符合条件的申请按钮；商家经营报表本店隔离。权限明确、动作理由/状态/模拟标识可见、分页/空/错/重试及手机布局可用。界面不提供无限制改金额或状态输入框。

## 验收

真实PG权限（customer/owner/staff/demo/reviewer均非platform）、对象归属、举报目标可见性、重复、不可自裁、并发/重试、冻结竞争状态、APPROVE金额/库存/退货安全、报表成功事实/区间口径/多店隔离；真实浏览器举报→平台处理→客户看到限制，售后拒绝→争议→平台批准→模拟退款→报表一致；全部既有数据库/前端回归和原有运行数据逐行升级保留。
