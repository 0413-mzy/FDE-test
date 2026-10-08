# 手动物流场景控制验证

日期：2026-10-08。候选codex/commerce-logistics-control，依赖codex/commerce-data-center；不合并main，不自动公开部署。

## 本机数据库与真实HTTP

原数据库增量升级到0010_logistics_control。迁移前后比较43张业务表的496条旧记录及旧列哈希，完全一致；仅添加可空元数据和扩大物流阶段约束。历史事件没有补造location/reason/actor/request_version。

新建虚构商品与订单后创建包裹，真实HTTP验证：拒绝待揽收直接签收；揽收→运输→延误→恢复运输→派送→失败→重新派送→签收。补充早期揽收事件的status_applied=false，当前状态不倒退；复用事件编号与同一完整请求重报，轨迹和版本不增加。

客户/商家读取同一包裹轨迹，签收后订单仍SHIPPED，确认收货独立；demo列表可查已签收包裹。客户与商家无demo读取权限403。轨迹包含发生与接收时间、模拟来源、操作者、地点、原因和状态是否应用。

验收包裹64308928-981d-41d3-a618-35a36f8f2657有10条轨迹，所有本轮业务资料虚构。另建待揽收包裹67431570-68af-4114-b300-bd84557c8821供用户手动演示。没有重置或修改此前订单。

## 浏览器限制

CUA访问本机5179被管理员策略验证服务不可用阻挡。没有使用其他UI自动化、代理、关闭安全设置等绕过。真实页面点击、截图与视觉验收尚未通过；HTTP验证不替代浏览器验收。公网仍为已发布的数据中心版本。

## 自动验证与独立审查

冻结版本前端33项测试、ESLint、TypeScript与Vite构建通过；Ruff check通过，110个Python文件format检查通过。新增9项真实PostgreSQL物流测试及既有历史迁移往返测试10 passed。独立规格审查通过；质量审查发现并修复提交成功提示因刷新而卸载的问题，复审通过。新增快照保持/账号与包裹隔离测试；刷新或读取失败时禁止新动作，仍可安全重试原请求。最终完整后端：436 passed、35 deselected、543.83秒；一项既有Starlette依赖弃用警告。命令`python /private/tmp/fde-shopping-target.py -m "not integration" -q`。35项可选旧Sandbox外部集成不计为接受。前端命令npm test / npm run lint / npm run build。文档链接、diff whitespace与私密凭据扫描通过。

最终本机API重启后，原验收包裹10条事件仍可读取。新揽收事件只写一条Shipment历史，before/after版本递增且状态一致；重复上报不增加轨迹。第二个手动演示包裹当前COLLECTED，可从运输继续。
