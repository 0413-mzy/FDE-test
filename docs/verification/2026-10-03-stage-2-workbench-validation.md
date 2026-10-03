# Stage 2 静态工作台验证

日期：2026-10-03。候选分支：`codex/core-workbench-shell`；基线 `cc2f262`，
依赖 Stage 1 契约 PR #2。用户授权自动执行 Stage 2 候选；审查/合并出口保留。

## 实现与观察范围

- 六个虚构 Contract Context：正常、多包裹、旧数据、局部超时、未知来源时间、来源冲突。
- 咨询列表/详情、逐包裹来源与更新时间/抓取时间/事件发生时间、原仓库备注、来源查询结果。
- 来源失败不改成业务异常；冲突保留两边原信息；未知时间不显示为实时。
- 本地草稿编辑和恢复示例；Validation 显示未执行，批准一直禁用，没有发送入口。
- Loading/Empty/Error 是预览状态。没有 Product 或 Sandbox 业务 HTTP 请求。
- 运行时只从 frontend build context 的本地 JSON 读取预计算示例，浏览器测试与契约 JSON
  做严格一致性检查。没有 Evidence Engine/CaseContext resolver 或事实生成。

## 本地执行结果

| 命令 / 检查 | 结果 |
| --- | --- |
| `npm run lint` | 通过 |
| `npm run typecheck` | 通过；包含 Playwright 配置和测试 |
| `npm run build` | 通过；Vite 31 modules，JS 269.56 kB，gzip 78.34 kB |
| `PLAYWRIGHT_CHANNEL=msedge npm test`（PowerShell 环境变量） | 13 passed，8.6s，无 skip/retry |
| 浏览器人工查看 | 本地 15174 预览，桌面列表/证据/草稿布局正常 |

13 项测试包含 fixture parity、初始来源时间、不同包裹状态、旧更新时间、局部超时、未知时间、
两边冲突、Loading/Empty/Error 三种预览、编辑/恢复且批准禁用、零业务 fetch/XHR、
390×844 移动端无横向溢出。

默认沙箱构建曾因 Windows 写权限失败；经允许的 workspace 写入重新执行后通过。
这不是测试失败。无需安装本机系统服务。

## CI 与未完成项

CI 配置新增 Chromium 安装和 `npm test`；创建 PR 后验证 Linux Chromium 结果并更新记录。
本机无 Docker，容器 build/start 未验证；Compose config 在 CI 单独验证，不能替代启动。
没有认证、业务 API、AI、持久化编辑、校验/批准行为，不能据此宣称 Core MVP 已完成。
两名开发者 Review、main 保护和 main 合并仍未完成。
