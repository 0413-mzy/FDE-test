# 用户与商家入驻扩展验收

日期：2026-10-07（Asia/Kuala_Lumpur）。用户选择先补用户/商家入驻，并明确本地模拟邮件、部署前接真实服务。
基于第五步f26b371，分支codex/commerce-user-merchant-onboarding；不合并main、不部署、不进入AI。

## 实际产出

- 18个新增commerce操作：注册/验证/恢复、资料/邮箱/密码、地址簿、入驻申请/撤回/独立审核；总计70个操作。
- 注册验证后仅客户；独立reviewer批准才原子创建新店与OWNER，新店连接原商品、库存与购物流程。
- 账户中心、验证/恢复入口、地址簿预填及审核界面；重置/修改密码撤销旧会话，历史订单快照保持。
- 冻结增量0005新增六表，显式reviewer Seed；旧0001–0004迁移未改变。
- development/test私有模拟邮箱：目录0700、邮件/独立HMAC密钥0600，无HTTP码查看器，无真实投递。
- 原事务记录投递pending：并发原key重试返回忙，失败保持503、新key重发恢复，避免重放假成功。

## 验证

| 检查 | 本次结果 |
| --- | --- |
| 入驻专项真实PG | 12 passed，0跳过，最终冻结迁移版本17.23秒 |
| 全数据库真实PG回归 | 203 passed，11外部HTTP integration deselected，0失败/跳过，205.91秒；含原商城70和入驻12 |
| 非database/nonintegration后端 | 161 passed，0跳过 |
| 运行器安全测试 | 5 passed |
| 前端测试/lint/typecheck/build | 16 passed，静态检查和构建通过 |
| 入驻真实Chrome | 最终8/8检查通过；注册至新店购买、恢复撤销旧会话、一码一次、刷新持久化、浏览器无凭证持久化 |
| 原场景与入驻全回归 | 八个fresh-schema场景通过；44组命名检查另加完整购买流程，16个HTTP边界检查，无页面错误 |
| API重启 | 八场景各一次，共9订单完整视图保持；最终入驻单独重跑保持1订单 |
| 原用户演示库升级 | 0005升级和独立reviewer Seed前后，28张旧commerce表全部原记录/字段逐行一致 |
| 本机原地址 | 18008 API/5179 UI可用；70操作与6个虚构身份的授权GET/退出检查通过，没有业务写入 |

入驻专项覆盖：验证码用途/过期/一次使用、匿名限额/错误尝试计数、精确重放/换body冲突、
密码空白与全部旧会话撤销、邮箱绑定保留旧邮箱、地址20条上限/默认唯一/替换版本/所有权、
并发注册/批准、审核撤销后锁等待复查、拒绝理由/撤回、投递阻塞期间同键并发和失败后重启恢复。
独立审查发现并修复默认地址版本、失效邮箱预留、审核缓存、凭据空白、重放状态、投递窗口、
密码指纹和前端恢复锁；没有以mock代替PostgreSQL验收。

命令（backend，显式独立TEST_DATABASE_URL）：

```sh
python -m pytest tests/database/test_onboarding.py -q
python -m pytest tests/database -m 'not integration' -q
python -m pytest -m 'not database and not integration' -q
```

根目录：`python -m unittest discover -s scripts/tests`、`ruff check backend scripts`、
`ruff format --check backend scripts`、`node --check scripts/commerce-onboarding-browser-acceptance.cjs`。
前端：`npm test`、`npm run lint`、`npm run typecheck`、`npm run build`。
真实Chrome：`python scripts/commerce-demo.py --scenario all`及最终`--scenario onboarding`，
均显式设置隔离URL/Playwright/Chrome，不接真实资金或邮件。

[最终入驻浏览器证据](commerce-onboarding/browser-results.json)、
[八场景回归证据](commerce-onboarding/regression-browser-results.json)、
[新店购买截图](commerce-onboarding/new-shop-purchase.png)、
[持久账户截图](commerce-onboarding/persistent-account.png)。浏览器证据保存实际父HEAD和dirty/source-tree哈希；
不是声称已提交HEAD的历史执行；后续文档、冻结DDL/seed互斥和默认地址复选框宽度调整有相应迁移回归或构建检查。

## 边界与GitHub

邮件、支付、物流、退款均模拟，现链接只在本机。真实资质校验、真实邮件服务、生产队列和部署未完成。
正常/整体邮箱故障的已知/未知受理一致；提交后的单次投递故障返回闭合503，因此该故障下不保证
完全掩盖邮箱存在性。无公网暴露；部署前需重新设计真实投递故障与抗枚举。
本机未安装Docker，Compose以准确HEAD CI为准；外部Sandbox HTTP集成35项本次未执行，
该模块未改动，不能把历史通过当本次接受。全数据库命令排除其11项依赖外部HTTP的测试。
实现6014da4交付[Draft PR #7](https://github.com/0413-mzy/FDE-test/pull/7)，依赖第五步PR #6，仍为OPEN/Draft；不合并main。
准确HEAD CI状态在交付前通过GitHub逐项核对。

全数据库首次执行201 passed、2 failed、11 deselected（200.80秒）：两个失败均为0005未实现隔离测试
所需downgrade往返。已补六张新增表的逆序drop，不改变旧迁移；隔离迁移/售后17项重跑通过。
此回退只用于新测试schema，原用户库只执行upgrade。修复后全量203项全部通过；准确HEAD CI另行记录。

## 实现提交CI

6014da4eda7957db2e91f524fdbbfa4a4e2b5d7e：push与PR的backend、frontend、database、compose全部SUCCESS。
[PR运行37580067591](https://github.com/0413-mzy/FDE-test/actions/runs/37580067591)与
[push运行37580043597](https://github.com/0413-mzy/FDE-test/actions/runs/37580043597)均已completed/success。
此后文档收尾提交仍须核对PR准确HEAD CI，不将此实现提交的检查冒充后续提交结果。
