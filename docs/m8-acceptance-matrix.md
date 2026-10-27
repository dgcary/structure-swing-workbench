# M8 Web 交易工作台｜独立验收证据矩阵（进行中）

> 范围：Notion TSK-18 / GitHub Issue #9 / PR #19。此文档只记录已实现与尚未满足的要求；不是审核通过证明，也不构成合并、部署或交易授权。CI 结果须以 PR 最新 HEAD 的 GitHub Actions 为准。

## 一、九项首页指标

| 指标 | 来源与代码证据 | 当前结论 |
| --- | --- | --- |
| 账户总权益 | `backend/app/workbench/overview.py`；M5 账户 CSV 临时账本，或显式开启持久化读取后从 `AccountSnapshot.total_equity` 投影 | 部分通过：仅已标注来源、时间的值可展示；非实时 |
| 可用资金 | 同上，`AccountSnapshot.available_cash` | 部分通过：来源不足仍为“未接入” |
| 当前总仓位 | `backend/app/workbench/persisted.py`；同一账户快照中所有持仓市值与总权益均存在且数值自洽时计算 | 部分通过：尚无完整账户核验与真实数据库联调 |
| 持仓股票数 | 同一账户快照内正数量标的计数；空快照不伪装为零持仓 | 部分通过：仅代表该快照范围，不保证券商账户全量 |
| 当前账户总风险 | 尚无同时核验计划止损、真实持仓与风险暴露的完整数据路径 | **未通过** |
| 当日 T 次数 | 尚无可复核的持久化完整 T 闭环事实来源 | **未通过** |
| 未完成 T 循环 | 尚无可复核的持久化未闭环周期来源 | **未通过** |
| 日内换仓状态 | 尚无已核验的换仓事实模型/来源 | **未通过** |
| 当前最高审计等级 | 只读持久化审计记录投影，需带时区的来源时间 | 部分通过：历史记录不等于当前动作审计许可 |

**边界：**所有无来源、时间不合格或计算条件不充分的指标必须为 `unavailable`，不能填零或通过。代码：`backend/app/workbench/overview.py`、`frontend/src/overviewContract.ts`。

## 二、计划、动作、审计与持仓

| 验收项 | 证据 | 当前结论 |
| --- | --- | --- |
| 正式有效计划 | `persisted.py` 只读取 `TradePlan.is_active` 与有效版本；`App.tsx` 显示失效价、第一目标、版本与来源 | 部分通过：缺真实 PostgreSQL 数据联调；风险仍未知 |
| 已记录未完成动作 | 从正式有效版本读取计划中/已审计/执行中/部分成交的动作；全部 `executable=false` | 部分通过：缺经核验的计划执行日期，**不能称为今日待办** |
| 正式历史审计 | 从正式版本/动作关联的 `AuditResult` 读取；非通过项优先、通过项折叠；始终不可执行 | 部分通过：历史审计不等于当前实时审计，尚无完整可执行性判定 |
| 核心仓/T仓 | 仅同一 `PositionSnapshot` 的 CORE、T 两类桶都存在、非负且数量严格对账时显示 | 部分通过：没有可卖数量/T+1 的来源验证 |
| 账户与持仓快照 | 只读投影、显式来源与时间；无时区的时间不冒充可验证事实 | 部分通过：SQLite 丢失时区时主动隐藏，需真实 PostgreSQL 联调 |
| 账户 CSV | `account_snapshot_preview.py` 仅处理请求内隔离账本，`persisted=false`，`full_account_verified=false` | 通过静态和自动测试；未做真实账户数据实机验收 |
| 无自动下单 | 后端总览与全部计划/动作/审计投影保持 `trade_execution_enabled=false` / `executable=false` | 通过静态审查与单元测试，不等于交易规则整体通过 |

持久化读取必须显式启用 `WORKBENCH_PERSISTED_READ_ENABLED=true`，并提供已迁移且可连接的 `DATABASE_URL`。默认关闭，不会自动创建账户记录或连接券商；数据库不可用时按未知数据降级。真实环境中**禁止把演示数据当作真实账户**。

## 三、页面与测试证据

- 首页：`frontend/src/App.tsx`；中文导航涵盖总览、计划管理、审计结果、K线、成交导入、T仓、历史计划、复盘、研究样例。
- 本机草稿与复盘：`LocalPlanDrafts.tsx`、`LocalReview.tsx`；相关本机存储与版本测试位于 `frontend/tests/`。
- 只读来源协议：`frontend/src/overviewContract.ts`、`frontend/tests/overviewContract.test.mjs`、`frontend/tests/persistedOverviewContract.test.mjs`。
- 后端数据与无来源保护：`backend/tests/test_workbench_overview.py`、`test_workbench_holdings.py`、`test_workbench_persisted_projection.py`。
- 已核验的阶段 CI：提交 `233871ee` 对应的 Actions 成功，前端 88 项、后端 386 项通过；**最新 HEAD 仍须重新确认**。
- **未完成实机证据**：手机宽度截图、全部导航入口人工点击、真实 PostgreSQL 时区/快照联调、真实 CSV 样例对账。不得把这些标记为 PASS。

## 四、当前 Gate

**M8 暂不通过，PR #19 保持 Draft，不合并、不部署、不启动 M9。**

下一轮仅在原分支继续补齐：账户风险、T 闭环/换仓可追溯来源、今日动作日期语义、实际数据接入与完整移动端验收。不得凭历史审计、草稿、模拟行情或推断价格生成交易许可；如所需模型字段与既定规则发生冲突，先记录阻塞而不是擅自修改交易体系。
