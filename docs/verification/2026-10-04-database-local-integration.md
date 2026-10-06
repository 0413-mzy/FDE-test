# 数据库整合与本机验证（2026-10-04）

用户确认执行数据库整合、本机启动、迁移和 Seed 验证，检查通过后合并数据库候选。
本次不新增 API、AI、Evidence 或前端行为。

## GitHub 整合

- [PR #6](https://github.com/Mark-UM/FDE-test/pull/6) 已 merge 到 `codex/core-database`，
  合并提交 `401de8b48ab947e6b08fc6498cd2b836adc94147`。
- [契约 PR #2](https://github.com/Mark-UM/FDE-test/pull/2) 已 merge 到 main，
  合并提交 `a636bcdc4aa0501f7330bc0da5d45f3782cd4c25`。
- 本地 `codex/core-database-integration` 以普通 merge 同步 main，提交
  `fafb7b278ac113b35669b166bf9ff5ef9efa2b97`，非强推到数据库候选分支。
- [PR #3](https://github.com/Mark-UM/FDE-test/pull/3) base 已改为 main；无分支删除。
  合并前须本记录所在提交的全部 checks 成功。最终合并状态以该 PR 为准。
- 同步后的 [CI run 37183629099](https://github.com/Mark-UM/FDE-test/actions/runs/37183629099)
  四任务成功：57 PostgreSQL tests passed（36.66s，无 skips）、66 backend tests passed，
  Ruff lint/format、frontend lint/type/build、Compose config 全通过。

## 本机环境变更

本机原无 PostgreSQL/Docker。Homebrew 安装 `postgresql@17`，版本 **17.11**。
安装同时更新了相关依赖、自动清理旧依赖版本和缓存；旧版本可用包管理器重新安装，
未删除项目文件或用户数据库。Homebrew 默认新建 `/opt/homebrew/var/postgresql@17`，
本次没有启动它，也没有注册开机服务。

实际验证使用独立目录 `/private/tmp/fde-pg17-b4ZOHL`，目录权限由 mktemp 限定：

- PGDATA：`/private/tmp/fde-pg17-b4ZOHL/data`。
- Unix socket：`/private/tmp/fde-pg17-b4ZOHL`，port 55437。
- `listen_addresses=''`，无 TCP 监听；本机 socket trust，host 配置 SCRAM。
- 仅虚构测试角色 `fde_local_test`、新库 `fde_core_validation`；未访问其他数据库。
- 测试为每条用例建立独立 `fde_test_<uuid>` schema，只清理该 schema。

## 实际执行与结果

从仓库 `backend/`，Python 3.12 隔离环境 `/private/tmp/fde-review-venv`：

```sh
export DATABASE_URL='postgresql+psycopg://fde_local_test@/fde_core_validation?host=/private/tmp/fde-pg17-b4ZOHL&port=55437'
export TEST_DATABASE_URL="$DATABASE_URL"
export APP_ENV=test
/private/tmp/fde-review-venv/bin/python -m alembic upgrade head
/private/tmp/fde-review-venv/bin/python -m alembic current
/private/tmp/fde-review-venv/bin/pytest tests/database -q
```

- 空库迁移成功，当前版本 `0002_nonblank_constraints (head)`。
- 本机真实 PostgreSQL：**57 passed，29.40s，无 skips**。
- 实际 Seed CLI 通过 subprocess 执行两次；每次 password 由 secrets 临时随机生成，
  未输出、未持久保存。第二次使用不同临时 password。
- SQL 查询/assert 验证 **12 张工作流表、2 个 team、5 个 user、12 个 Inquiry**。
- 两次 Seed 之间，在这个测试库将一条 Inquiry 标为 ESCALATED、lock_version=4；
  第二次 Seed 保留状态/版本/创建时间以及原 user password_hash。
- 一次临时验证脚本因无用的 `app.config` 导入而失败，尚未执行 Seed；删除该导入后
  完整重跑并得到上述通过结果。未因此修改项目实现。
- lint 通过，30 个 Python 文件格式检查通过。容器构建/启动未验证。

## 安全交接与限制

验证后关闭本次临时实例，不删除目录或测试数据。可用下列命令重新启动/停止（目录
位于系统临时区，可能被系统清理，不能作长期开发库或备份）：

```sh
/opt/homebrew/opt/postgresql@17/bin/pg_ctl -D /private/tmp/fde-pg17-b4ZOHL/data -l /private/tmp/fde-pg17-b4ZOHL/server.log -o "-k /private/tmp/fde-pg17-b4ZOHL -p 55437 -c listen_addresses='' -c timezone=UTC" start
/opt/homebrew/opt/postgresql@17/bin/pg_ctl -D /private/tmp/fde-pg17-b4ZOHL/data stop -m fast
```

这个库仅用于验收；已有账号的随机密码未保留，不作为可登录 Demo 环境。
后续长期开发库应重新建库，并由负责人显式提供开发密码，不修改现有密码哈希。
数据库并未接入 API 启动；`/health` 不证明数据库连通。服务级并发、跨 Inquiry/team
授权、真实容器运行仍属后续交付。旧非法历史使 0002 升级失败时不得自动改写历史。
前次修复 RED/GREEN 证据见 [审查记录](2026-10-04-database-review-fixes.md)。
