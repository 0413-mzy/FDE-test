# 第四步：消息与售后验收

日期：2026-10-07。基于第三步提交 `0e50df5575571981a4a3491183293fcf262efb13`，
候选分支 `codex/commerce-messages-after-sales`。用户明确授权第四步；不合并main，不进入第五步或AI。
切片见[实现边界](../commerce/step-4-implementation.md)，规则见[commerce-v1](../commerce/README.md)。

## 新增实现

- 16个冻结消息/售后/退款操作；商城总计52个HTTP操作，旧客服命名空间独立。
- 6个新商城表，增量0004迁移；会话绑定不可改、消息/申请明细只追加、退款尝试终态不可反转。
- 通用及订单会话、客户/商家纯文本消息、刷新分页；身份与对象权来自当前服务端会话。
- 部分/全额未发退款、已送达商品14天内退货退款、OWNER审批/退货接收/明确回库决定。
- 窄DEMO退款成功/失败，失败后OWNER可重试；金额由购买快照计算，回库和退款不会重复发生。
- 订单店铺名称、人工模拟付款/退款提示；旧幂等响应保留原始形状，不回填shop_name。

## 本次命令与结果

完整后端回归371项通过（260.51秒、0跳过）；随后只补充3个验收测试，
补充后的Step4专项16项全部通过（36.57秒）。两次运行没有业务源码变更，
最终提交的全部测试由GitHub CI再次执行。唯一警告是已有Starlette/httpx弃用提示。

| 检查 | 本次结果 |
| --- | --- |
| 后端完整回归 | 371通过、0失败/跳过，包含真实PostgreSQL与13项独立Sandbox HTTP |
| Step4真实PostgreSQL测试 | 初始RED→GREEN；补充后16项通过，含5处退款回滚注入、真实强制重叠请求和额外拒绝/历史场景 |
| 前端 `npm test` | 13通过、0失败/跳过；3个新增规则测试先RED后GREEN |
| 前端 lint/typecheck/build | 通过，0 ESLint警告 |
| Ruff lint/format | 通过；65个Python文件格式符合 |
| 第四步真实Chrome | 5个全新schema场景通过，31次检查（含重复公共检查），0页面错误 |
| 原第三步Chrome回归 | 两店订单、两付款、三包裹、两订单确认收货通过；0页面错误 |
| 本机Compose | 未执行：本机没有Docker；最终提交Compose配置以GitHub CI为准 |
| 现有演示库升级/重启 | 通过；0004迁移前后订单、行数量、库存、支付、包裹及库存流水完全一致 |
| 升级后真实HTTP | 52个操作、5类身份、旧订单店铺名/售后视图、消息列表、退款队列及原前端地址通过；无业务写入 |

后端命令在backend目录：

```sh
TEST_DATABASE_URL='<显式隔离测试PostgreSQL连接>' python -m pytest -q -p no:cacheprovider --sandbox-url http://127.0.0.1:19007
ruff check .
ruff format --check .
```

PostgreSQL 17为本机独立测试实例，SQL测试每项新建并只清理 `fde_test_<uuid>` schema。
浏览器使用另建 `commerce_step4_qa_<uuid>` schema和虚构Seed；不读取/改动用户现有runtime订单。
独立Sandbox由另一个checkout运行，通过真实HTTP验证旧集成；没有Product导入Sandbox或读其数据库。
前端使用真实API、内存Bearer，额外浏览器断言仅授权GET订单/库存；没有前端假业务数据。

## 双端正常场景映射

| 场景 | 状态 | 本次证据 |
| --- | --- | --- |
| C12 通用/订单会话、双向消息持久化 | PASSED | 五个浏览器场景分别创建会话，商家回复，新会话重新登录读取；[消息截图](commerce-step-4/messages.png) |
| C13 部分未发退款 | PASSED | partial-return：2000分购买退款1000，库存3→4，财务部分退款 |
| C14 全额未发退款 | PASSED | full-refund：退款2000，库存3→5，订单CANCELLED/REFUNDED；[截图](commerce-step-4/full-refund.png) |
| C15 发1件、退款未发1件 | PASSED | shipped-partial-refund：只回库1，订单SHIPPED；[截图](commerce-step-4/shipped-partial-refund.png) |
| C16 送达后退1件并回库 | PASSED | partial-return：收到退货时库存4→5，退款后仍5，原包裹DELIVERED；[客户](commerce-step-4/customer.png)/[商家](commerce-step-4/merchant.png) |
| C17 退货不回库 | PASSED | return-no-restock：接收与退款库存均为3，退款1000；[截图](commerce-step-4/return-no-restock.png) |
| C18 拒绝与撤销 | PASSED | reject-withdraw：两个终态历史，无退款尝试，金额/库存不变；[截图](commerce-step-4/reject-withdraw.png) |
| C19 失败后重试 | PASSED | partial-return：第一尝试FAILED，Case仍REFUND_PENDING；OWNER新尝试成功且只退款一次 |

每个浏览器场景使用独立customer/OWNER/DEMO上下文；另外登录STAFF只读售后、隐藏店主动作。
包含HTML样式文本的消息未生成img或执行脚本，也未建立任何售后记录（P18）。
390px移动端无横向溢出；[移动截图](commerce-step-4/mobile.png)。

## 权限、事务与审查

当前新增数据库测试直接验证客户消息越权404、STAFF审批403、授权优先于坏JSON、
店铺暂停时既有订单会话/售后可处理且新通用会话拒绝、成员撤销后原key重放拒绝。
活动未发售后阻止发货，活动售后阻止地址修改；退款数量和严格整数校验保留后端边界。
14天窗口包含等号，申请后跨过窗口仍可审批；确认退货与事件重复不二次回库。
原第三步幂等checkout缺shop_name仍精确重放；当前GET返回新字段。
补充测试直接验证第二活动Case ACTIVE_CASE_EXISTS、客户绑他人订单/嵌套错单错店404、
选中行未全部送达INVALID_STATE、窗口超过1秒RETURN_WINDOW_EXPIRED、登记退货后撤销/收货前退款拒绝。
COMPLETED订单退货退款保留completed_at/原shipped_qty/配送历史，restock=false不增加库存或库存版本，
已退款数量再次申请QUANTITY_CONFLICT。

R11：强制售后先获得锁、发货请求等待，后者VERSION_CONFLICT，不发生部分发货。
R12：强制两次接收退货重叠，只有一次RETURN_RESTOCK；两审批重叠不能把REJECTED改回批准。
R14：退款成功处理中分别于库存、订单、尝试、事件和Audit注入失败，整单视图、
库存/流水、事件及成功key均回滚；原key重试和重放只提交一次。

独立审查发现并修复两个后端问题：锁等待后的Case缓存旧状态、事件重放未先检查version格式。
前端审查发现售后版本冲突未重新GET，已补刷新，不自动重提写入。
所有成功写入仍使用短数据库事务和schema局部写互斥；这是低吞吐MVP取舍，没有网络持锁。

## 可复现浏览器命令

详见[开发说明](../development.md)。为每个场景另建schema/迁移/显式Seed，配置仅本机可读的密码文件：

```sh
COMMERCE_UI_URL='<隔离前端地址>' COMMERCE_PASSWORD_FILE='<本机密码文件>' \
COMMERCE_SCENARIO=partial-return node scripts/commerce-step4-browser-acceptance.cjs
```

另外四个场景名为full-refund、shipped-partial-refund、return-no-restock、reject-withdraw。
需要已安装Playwright模块/浏览器；跨平台时显式设置CHROME_EXECUTABLE。
脚本不重置数据。首次调试失败来自未刷新商家旧列表、带选项文本的select标签精确匹配；
修正等待/选择器后五个全新schema通过，没有把失败尝试算成通过。

## 交付限制

不是54项全业务矩阵全部覆盖或实际经营上线证明。消息刷新读取，无推送/附件/已读。
退货一次接收全部申请数量，无部分验货/争议仲裁/换货。模拟退款需要DEMO明确提交结果，
没有真实资金、承运商、外部消息投递或AI。没有定时自动审批、自动退款或自动确认收货。
GitHub交付为依赖第三步的草稿PR；最终SHA与CI结果以该PR检查为准，不能把历史CI当作当前检查。
