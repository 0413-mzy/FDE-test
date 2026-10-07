# 商品与购物体验设计

用户2026-10-07请求补全图片上传、分类、搜索筛选、收藏、评价；沿用此前全权执行授权和既有模拟商城边界。此设计是授权范围内的实施决定，不新增真实支付、部署或AI。

## 模块与数据

增量0007：Category（名称、active）、ProductExperience（product唯一、category可空）、ProductImage（product、排序、alt、mime、width/height、校验摘要、规范化图片BYTEA）、Favorite（customer/product唯一、active）、ProductReview（customer/order_line唯一、product/shop/order关联、1–5星、纯文本、商家回复、visible）。全部Record有创建/更新时间/version；明确外键/唯一/约束。新表安装安全历史触发器，图片二进制不复制到历史，仅保存元数据。不改写0006/原有订单行快照。

图片初版本机数据库存储，避免文件与事务不同步；PNG/JPEG/WebP，单张原始最多3MiB、最多8张，像素上限与Pillow实际解码/重编码，去元数据，拒绝SVG/伪格式/解码炸弹。HTTP闭合JSON base64专用有界请求，先授权后解码；输出安全图片ID/平台URL，无任意外部抓取。公开读取仅公开商品与ACTIVE店铺；OWNER可读本店草稿，隐藏或下架后的私人图片不公开。图像响应防嗅探与适当缓存策略。

普通商品接口保持原契约。新 `/shopping/products` 提供搜索、店铺、分类、最低/最高价（整数分）、仅有货、排序（newest/price_asc/price_desc/rating）、分页。价筛选按同一可购买SKU匹配，不把两个不同SKU的最低/最高条件混用；评分仅可见购买评价聚合。搜索名称/描述不把输入当SQL，空结果与非法参数可解释。

分类由平台管理；已有未分类商品正常可售。OWNER指定分类/维护图片，非本店/STAFF拒绝。客户收藏自己的商品，重复设置幂等；下架商品显示不可购买且不能绕过目录权限。已完成订单的购买者每条订单行可评价一次，评分1–5、正文1–2000；购买关联由后端验证，不准评价他人订单/未收货/非该商品；用户可改自身评价，商家仅回复本店评价，平台可隐藏违规评价但保留历史。纯文本安全呈现。完整退款仍显示真实购买关联及售后信息，不假造销量。

## HTTP/UI 对接

新router购物体验命名空间保持 `/api/commerce/v1`。
- GET /shopping/categories，GET /shopping/shops：公开有效分类/店铺完整分页，不从前100商品猜店铺。
- GET /shopping/products，GET /shopping/products/{product}：ProductCardView（原ProductView字段+category_id/category_name/images/rating/review_count）。
- GET /shopping/products/{product}/reviews；GET /shopping/images/{image}（二进制，按可见性判定）。
- GET /customer/favorites；POST /customer/favorites：{product_id,active}。
- POST /customer/orders/{order}/lines/{line}/review：{rating,body}；POST /customer/reviews/{review}/edit：{expected_version,rating,body}。
- GET /merchant/shops/{shop}/reviews；POST /merchant/shops/{shop}/reviews/{review}/reply：{expected_version,body}。
- GET/POST /merchant/shops/{shop}/products/{product}/experience：设置category_id，expected_version使用Product.version；图片上传POST同一base/images：{expected_version,data_base64,alt}；图片删除POST base/images/{image}/delete：{expected_version}。

所有写入用原Commerce写锁/授权/幂等，理由与请求/操作者落历史。ProductCardView图片含id/url/alt/position；分页用原Page结构。前端保持现有选物视觉，接真实图片、商品详情/评价、价格/分类/库存/排序、收藏入口、订单评价、OWNER图片区/分类选择/评价回复；重试与账户切换遵循原CommerceClient机制。

## 验收

真实PG：过滤/分页/价格同SKU/可见性；OWNERSCOPE；图片合法及非法/大小/像素/隐藏/事务失败；收藏隔离/重放；完成订单评价、重复/越权/无效状态、编辑/回复/隐藏；新表历史及旧行保存；原有购买/售后回归。真实HTTP/Chrome至少覆盖上传→公开显示→分类搜索→收藏→完成购买评价→商家回复。不将旧文字搜索冒充新增实现。
