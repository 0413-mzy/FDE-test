# 公开演示部署验证

日期：2026-10-07。公开演示已发布：<https://fde-commerce-demo.onrender.com/>。
代码保留在[Draft PR #10](https://github.com/0413-mzy/FDE-test/pull/10)，未合并 main。

- 后端非数据库回归：173 passed（含限流回归）。
- 真实 PostgreSQL17 隔离模式：233 passed，11 deselected（独立 Sandbox 集成）。
- 前端：21项测试，以及 lint/typecheck/build 通过。
- 本机生产入口、实际增量迁移和独立 seed 已启动；真实 HTTP 完成静态资源、
  私密管理账号隔离、公开写入限制、跨客户/店铺权限、图片上传、模拟购买与履约。
- 重启同一生产服务后，完成订单与上传图片仍可读取；不修改原本机业务库。
- 真实浏览器已确认公开提示、共享账号登录与账户敏感表单隐藏。
- 本机没有 Docker；容器构建/运行由 GitHub CI 实际验证，不声称本机 Docker 已通过。
- 8e99540 的 push/PR 容器 CI 已通过，实际镜像构建、生产交易与重启持久化成功。
- 用户确认改用 Render Free + Neon Free；允许凭据配置，但不创建付费服务或添加支付方式。
- Neon PostgreSQL18 独立库的0001至0008实际迁移、公开初始化与 `/ready` 成功。
- Render 首次部署 b143e78 成功；0f4d997（构建依赖补丁）重新部署状态 Live。
- 实际公网 HTTPS 的完整 HTTP 购买/模拟付款/发货/送达/收货、图片与客户/店铺权限通过。
- 重新部署后，原完成订单和上传图片仍可读取；原本机数据库未用于云端。
- 真实公网浏览器共享账号登录、购物车、虚构地址结账与订单页面通过。
- Neon 账户显示 Free Plan / $0 month；Render Hobby / Free，账单 Services $0.00，
  Payment Method 提供 Add Card，未添加支付方式。免费额度之外接受暂停，不自动付费。
- source-map-js 1.2.1 更新为1.2.2；前端全套复验通过，npm audit 为0漏洞。
- 8e99540 的 push/PR 五个任务均成功；最终文档 HEAD 的10项结果以 PR 检查为准。
- 原本机 API 已重启到最新代码，`demo-info.enabled=false`，正常开发模式保留。

配置、限制和备份恢复见[部署说明](../deployment-public-demo.md)。
