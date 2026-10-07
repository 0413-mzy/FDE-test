# 入驻增量契约 commerce-onboarding-v1

2026-10-07，用户选择用户/商家入驻类别及本地模拟邮件。独立增量0005；原commerce-v1冻结规则保持。
API前缀/api/commerce/v1，闭合输入/DTO。所有private对象身份和对象权限先于body校验，写锁等待后再次验证。
所有写入除登录后已授权改密码外按明确幂等契约；匿名注册/恢复受理必须可安全重试，不重复账号/凭据邮件。
CODE为至少32随机字节生成的一次性不透明字符串；15分钟有效、只存摘要、purpose隔离；失败不原文回显。
公开认证入口受理结果不返回账号存在性、id、token、验证码或密码。模拟邮箱是受保护本机文件，不是公开API。
新邮件投递环境COMMERCE_MAILBOX_DIR；development/test才可使用。未配置时公开注册/恢复/验证投递拒绝503，不能谎称发送。
所有邮箱新流程使用精确email大小写规范化、ASCII边界，不自动绑定既有Seed账号的邮箱。
公开入口明确限额（每IP/用途10分钟20次；每邮箱/用途15分钟5次），错误重试也要有界；不信任X-Forwarded-For。
邮箱/密码/验证码/地址不写BusinessAudit.safe_metadata。密码与会话原语复用现有实现。

## API

| 方法及路径 | 输入/权限 | 结果 |
| --- | --- | --- |
| POST /auth/register | 匿名；{username,email,password} | 202 {accepted:true,simulation:true}；重复/已占用统一受理，不授予角色 |
| POST /auth/verify-email | 匿名；{email,code} | 200 {verified:true}；注册验证激活CUSTOMER/Cart，绑定验证仅改邮箱 |
| POST /auth/verification-request | 匿名；{email} | 202受理；只向已申请但未验证邮箱重新发码 |
| POST /auth/password-reset/request | 匿名；{email} | 202受理；已知/未知相同，仅已验证邮箱可发恢复码 |
| POST /auth/password-reset/confirm | 匿名；{email,code,new_password} | 200 {changed:true}；成功撤销全部旧会话，码仅一次 |
| GET /account/profile | 当前active账号 | ProfileView；旧账号缺资料时返回version0默认视图，不写库 |
| POST /account/profile | 当前账号；{expected_version,display_name,phone} | ProfileView；display_name0..100、phone0..32 |
| POST /account/email | 当前账号且当前密码；{expected_version,email,current_password} | 202受理；新邮箱验证前旧已验证邮箱保持有效 |
| POST /account/password | 当前账号；{current_password,new_password} | 200 {changed:true}；撤销包括当前在内全部会话 |
| GET /customer/addresses | CUSTOMER；limit/offset | Page<AddressBookView>，仅本人有效地址 |
| POST /customer/addresses | CUSTOMER；{address,is_default} | AddressBookView201；第一条默认，至多20条有效 |
| POST /customer/addresses/{id}/edit | 本人；{expected_version,address,is_default} | AddressBookView；更新/默认切换同事务 |
| POST /customer/addresses/{id}/delete | 本人；{expected_version} | {deleted:true}；删除默认时确定选另一条，旧订单不变 |
| GET /customer/merchant-applications | CUSTOMER；limit/offset | Page<MerchantApplicationView>，本人历史 |
| POST /customer/merchant-applications | CUSTOMER且已验证邮箱；{shop_name,business_scope,contact_name,contact_phone,description} | MerchantApplicationView201；已是成员或有活动申请409 |
| POST /customer/merchant-applications/{id}/withdraw | 本人；{expected_version} | MerchantApplicationView，仅PENDING可撤回 |
| GET /review/merchant-applications | 当前独立review_enabled；limit/offset、可选state | Page<MerchantApplicationView>；无订单/地址簿/消息资格 |
| POST /review/merchant-applications/{id}/decision | 当前review_enabled；{expected_version,decision:APPROVE或REJECT,reason} | MerchantApplicationView；批准原子创建Shop+OWNER，拒绝需理由 |

POST应用、地址、资料等本人/审核写入使用现有Idempotency-Key与原body/版本精确重放；当前权限优先。
公开认证受理也要针对原key/body安全重放，不能跨用途或换body重放；不能重放密码/恢复成功来重新赋权。
实现若需要新增匿名幂等记录，要独立于既有非空actor_id记录；不改变旧已提交响应。
邮箱挑战重放不能重发邮件，确认重放只返回安全成功响应，不再次改密码/复活旧会话。

## DTO

ProfileView：{account_id,username,version,display_name,phone,email:string|null,email_verified:bool,review_enabled:bool}。
AddressBookView：{id,version,address:Address,is_default:bool,created_at,updated_at}；Address沿用CN结构。
MerchantApplicationView：{id,version,state,shop_name,business_scope,contact_name,contact_phone,description,
created_at,updated_at,decision_reason:string|null,shop_id:string|null}。
申请state为PENDING/APPROVED/REJECTED/WITHDRAWN。业务描述字符串输入去首尾空白，密码保留原空白；必填非空，
shop_name1..200、business_scope1..500、contact_name1..100、contact_phone1..32、description1..2000；拒绝reason1..500，批准reason0..500。
所有返回时间RFC3339 UTC。无需新增通用权限管理或原AccountView字段；profile独立暴露审核资格。

## 交互及角色

登录区新增注册/验证/忘记密码。注册成功后提示在本机模拟邮件中取得码，验证后明确登录。
账户中心提供资料、绑定邮箱、改密码、地址簿与本人入驻申请；申请列表显示等待/拒绝原因与获批店铺。
新审核员只新增审核页，不将DEMO或旧客服ADMIN映射为审核员。开发显式初始化独立reviewer账号。
获批后GET/auth/me刷新原身份视图获得shops，新店主进入原工作台。下单选地址簿预填原AddressForm，
保留本次编辑，旧订单购买快照不受地址/个人资料变化影响。

本地模拟邮箱的CLI需要操作者访问受保护目录；邮箱文件仅0600、目录0700，不开放匿名查看接口。
投递在业务提交后完成；若模拟投递失败，返回闭合错误且允许重新请求，不能回滚已经提交的账号或
谎称邮件已送达。过期/错误挑战、投递失败和进程重启纳入测试。无真实邮件投递或公网部署。

匿名及邮箱绑定幂等指纹使用私有持久HMAC密钥；不保存可用于离线猜测密码的普通body哈希。
首次与精确重放均保留原HTTP状态。提交后投递失败存储闭合503结果；同键保持失败，
操作者修复模拟邮箱后以新key请求验证重发或密码恢复。此失败是已确认邮件失败，前端解除原请求锁。

投递开始前在原业务事务保存pending标记；同键在投递完成前返回OPERATION_BUSY，成功后才受理成功。
进程若在投递期间中断，原key不能假称成功；操作者以新请求恢复。已知/未知邮箱在正常受理和
环境整体不可写时保持相同结果；提交后的单次投递故障仍返回明确503，因此故障情况下不保证
完全掩盖邮箱是否存在。部署接真实邮件前需要独立设计持久队列及抗枚举故障处理。
