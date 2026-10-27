# M8 Web 交易工作台｜独立验收证据矩阵（进行中）

> 范围：Notion TSK-18 / GitHub Issue #9 / PR #19。此文档只记录已实现与尚未满足的要求；不是审核通过证明，也不构成合并、部署或交易授权。CI 结果须以 PR 最新 HEAD 的 GitHub Actions 为准。

## 一、九项首页指标

| 指标 | 来源与代码证据 | 当前结论 |
| --- | --- | --- |
| 账户总权益 | `backend/app/workbench/overview.py`；M5 账户 CSV 临时账本，或显式开启持久化读取后从 `AccountSnapshot.total_equity` 投影 | 部分通过：仅已标注来源、时间的值可展示；非实时 |
| 可用资金 | 同上，`AccountSnapshot.available_cash` | 部分通过：来源不足仍为“未接入” |
| 当前总仓位 | `backend/app/workbench/persisted.py`；同一账户快照中所有持仓市值与总权益均存在且数值自洽时计算 | 部分通过：新增隔离 PostgreSQL 16 + Alembic 迁移 + 只读投影集成测试；真实券商账户与完整持仓仍未核验 |
| 持仓股票数 | 同一账户快照内正数量标的计数；空快照不伪装为零持仓 | 部分通过：仅代表该快照范围，不保证券商账户全量 |
| 当前账户总风险 | `persisted.py` 仅在全部有仓标的均有时间匹配的有效计划、CORE/T 精确分配、T=0、CORE 策略成本与失效价时，按历史快照计算 `(Σ核心仓数量×(策略成本−失效价))/权益×100%`；`test_workbench_persisted_risk.py` | **部分通过**：具备完整核心仓历史证据时可计算；含T仓、缺计划/止损/成本或时序冲突时仍为“未接入”，不能冒充实时账户风险 |
| 当日 T 次数 | 尚无可复核的持久化完整 T 闭环事实来源 | **未通过** |
| 未完成 T 循环 | 尚无可复核的持久化未闭环周期来源 | **未通过** |
| 日内换仓状态 | 尚无已核验的换仓事实模型/来源 | **未通过** |
| 当前最高审计等级 | 只读持久化审计记录投影，需带时区的来源时间 | 部分通过：历史记录不等于当前动作审计许可 |

**边界：**所有无来源、时间不合格或计算条件不充分的指标必须为 `unavailable`，不能填零或通过。代码：`backend/app/workbench/overview.py`、`frontend/src/overviewContract.ts`。

## 二、计划、动作、审计与持仓

| 验收项 | 证据 | 当前结论 |
| --- | --- | --- |
| 正式有效计划 | `persisted.py` 只读取 `TradePlan.is_active` 与有效版本，并按 A 股市场当日日期排除显式 `valid_until` 已过期版本；`App.tsx` 显示失效价、第一目标、版本与来源；CORE-only 且时序可核验时显示历史风险估算（元）；`test_workbench_persisted_risk.py::test_expired_effective_flag_does_not_publish_an_active_plan_or_risk`、`test_future_dated_snapshot_and_plan_do_not_authenticate_account_risk` | 部分通过：已过期版本及时间戳明显超前的版本不再作为当前有效计划展示，也不提供账户风险指标；无时区的 SQLite 记录仍仅作未认证历史展示；缺真实 PostgreSQL 数据联调、T仓风险及初始风险 |
| 今日人工计划动作 | 新增 `TradeAction.planned_for_date` 可空人工指定 A 股市场日期（Alembic 0004）；仅当动作记录时间可信且该日期等于上海市场当日时标记为“今日人工计划”，其他动作单独展示；全部 `executable=false` | **部分通过**：日期语义不再由 `updated_at` 猜测；已新增默认关闭、管理员令牌保护的正式日期录入/保存/刷新路径及 PostgreSQL 合成数据往返验证，仍缺真实账户与手机端验收，不构成交易许可 |
| 正式历史审计 | 从正式版本/动作关联的 `AuditResult` 读取；非通过项优先、通过项折叠；始终不可执行 | 部分通过：历史审计不等于当前实时审计，尚无完整可执行性判定 |
| 核心仓/T仓 | 仅同一 `PositionSnapshot` 的 CORE、T 两类桶都存在、非负且数量严格对账时显示 | 部分通过：没有可卖数量/T+1 的来源验证 |
| 账户与持仓快照 | 只读投影、显式来源与时间；无时区的时间不冒充可验证事实 | 部分通过：SQLite 丢失时区时主动隐藏；新增 PostgreSQL TIMESTAMPTZ 实库往返测试（合成数据），仍缺真实账户数据 |
| 账户 CSV | `account_snapshot_preview.py` 仅处理请求内隔离账本，`persisted=false`，`full_account_verified=false` | 通过静态和自动测试；未做真实账户数据实机验收 |
| 无自动下单 | 后端总览与全部计划/动作/审计投影保持 `trade_execution_enabled=false` / `executable=false` | 通过静态审查与单元测试，不等于交易规则整体通过 |

持久化读取必须显式启用 `WORKBENCH_PERSISTED_READ_ENABLED=true`，并提供已迁移且可连接的 `DATABASE_URL`。默认关闭，不会自动创建账户记录或连接券商；数据库不可用时按未知数据降级。真实环境中**禁止把演示数据当作真实账户**。

## 三、页面与测试证据

- 首页：`frontend/src/App.tsx`；中文导航涵盖总览、计划管理、审计结果、K线、成交导入、T仓、历史计划、复盘、研究样例。
- 本机草稿与复盘：`LocalPlanDrafts.tsx`、`LocalReview.tsx`；相关本机存储与版本测试位于 `frontend/tests/`。
- 只读来源协议：`frontend/src/overviewContract.ts`、`frontend/tests/overviewContract.test.mjs`、`frontend/tests/persistedOverviewContract.test.mjs`。
- 后端数据与无来源保护：`backend/tests/test_workbench_overview.py`、`test_workbench_holdings.py`、`test_workbench_persisted_projection.py`、`test_workbench_persisted_risk.py`（T仓/缺成本/缺计划/时序不一致均 fail-closed）；`test_future_dated_snapshot_and_plan_do_not_authenticate_account_risk` 验证未来日期快照/计划不得认证账户风险，允许最多5分钟设备时钟偏差。
- 最新已核验代码 CI：提交 `27337a21875023d66f2a44189b688764bac30ed2` 对应 [PR CI #40495411215](https://github.com/dgcary/structure-swing-workbench/actions/runs/40495411215) 完成 `success`；后端 410 passed、Ruff PASS，前端构建与测试 PASS（包含 PostgreSQL 16 实库合成数据测试）。未做真实账户或移动端实机验收，CI 通过不等于 M8 Gate 通过。
- **未完成实机证据**：手机宽度截图、全部导航入口人工点击、真实账户 PostgreSQL 快照联调、真实 CSV 样例对账。不得把这些标记为 PASS。

### 2026-10-27 增量证据：未来动作与未来审计不得冒充历史事实

- `backend/app/workbench/persisted.py`：带时区且超出5分钟时钟容差的未来 `TradeAction.updated_at` 不再作为已记录未完成动作展示；对应动作审计也不会借该动作进入展示。
- 同文件：带时区且超出容差的未来 `AuditResult.created_at` 不进入历史审计列表，也不参与“当前最高审计等级”的历史来源指标。
- `backend/tests/test_workbench_persisted_future_records.py`：覆盖未来动作、未来审计、正常历史记录三种情况；继续断言 `executable=false`、`trade_execution_enabled=false`。
- 本项属于 **时间来源可信度防护**，不等于已实现“今日待执行动作”日期语义，也不证明真实 PostgreSQL、T+1、T闭环、换仓或手机实机验收。最新提交的 Actions 必须另行核验，不能用旧 HEAD 的 CI 代替。

### 2026-10-27 增量证据：隔离 PostgreSQL 16 实库集成验证

- CI 后端任务新增 PostgreSQL 16 服务容器，并先执行 `alembic upgrade head`，再运行测试；不依赖生产数据库，也不需要真实券商账号。
- `backend/tests/test_workbench_postgres_integration.py`：在迁移后的真实 PostgreSQL 数据库中写入**隔离合成快照**、核心/T仓桶与正式计划；强制数据库往返，核验 TIMESTAMPTZ 保留时区、来源完整时的历史 CORE-only 风险，以及未来快照/计划 fail-closed。
- 测试记录始终位于回滚事务内，绝不保存测试账户数据，也不授权交易。无测试数据库时本地跳过，GitHub Actions 配置测试库后必须执行。
- 此项只证明**PostgreSQL 数据类型、迁移与只读投影集成**，不证明真实账户接入、真实 CSV 对账、T+1 可卖数量、T闭环、换仓或手机端可用。CI 结果以最新 HEAD 为准。

### 2026-10-27 增量证据：用户上传 CSV 的未来时间门禁

- `backend/app/workbench/account_snapshot_preview.py`：隔离导入账户、持仓、成交 CSV 后，检查全部事实与成交的来源时间；超过 UTC 当前时间 5 分钟容差的未来记录使整次预览返回 HTTP 422，不显示为已发生账户事实。只修改 M8 预览，不改变 M5 导入器或交易规则。
- `backend/tests/test_workbench_account_snapshot_preview.py`：账户、持仓、成交三类未来时间反例及小幅设备时钟偏差正例；全部保持 `persisted=false`、`realtime=false`、`trade_execution_enabled=false`。
- 代码 HEAD `27337a21` 的 [PR CI #40495411215](https://github.com/dgcary/structure-swing-workbench/actions/runs/40495411215) 已完成 success，后端 410 项测试及 Ruff 通过，前端检查通过。该修复不代表真实券商数据接入、T+1、T闭环或手机实机验收完成。

## 四、当前 Gate

**M8 暂不通过，PR #19 保持 Draft，不合并、不部署、不启动 M9。**

下一轮仅在原分支继续补齐：含T仓时独立止损风险、T 闭环/换仓/T+1可卖数量的可追溯来源、真实账户/CSV对账与完整移动端验收。不得凭历史审计、草稿、模拟行情或推断价格生成交易许可；如所需模型字段与既定规则发生冲突，先记录阻塞而不是擅自修改交易体系。


### 2026-10-27 增量证据：今日人工计划动作的日期来源

- `backend/app/db/models.py` 与 Alembic `0004_m8_action_planned_for_date`：为正式交易动作新增**可空、仅由用户明确填写**的 `planned_for_date`，不从创建时间、更新时间、行情或 AI 推断。
- `backend/app/workbench/persisted.py`：仅当动作的来源更新时间具备可信时区、未超出未来 5 分钟容差，并且用户日期恰好是上海市场当天，才标记 `date_status=today`。其他已记录未完成动作仍只读展示，日期不可信时 `planned_for_date=null`、`date_status=unverified`。
- `frontend/src/App.tsx` 和 `overviewContract.ts`：今日人工计划与其他未完成动作分组；拒绝缺日期、非法日期或缺可信时间却声称“今日”的协议数据。无今日计划不等于今日无事项；所有动作仍 `executable=false`。
- 此前增量仅完善**日期字段、只读来源与页面语义**；现已在下节补充正式动作的管理员授权日期写入，但仍未完成实时审计、真实账户对账或手机实机验收；不得判定整个“今日待执行动作”通过。CI 结果以最新 HEAD 为准。

### 2026-10-27 增量证据：正式动作人工日期写入（安全默认关闭）

- `backend/app/workbench/action_date.py`、`backend/app/main.py`：仅对**已有正式有效计划**下、状态为「计划中」的动作开放人工日期更改或清除；校验原动作来源时间、计划有效性、日期格式与 `expected_as_of` 乐观并发版本，并在 PostgreSQL 行锁内修改。已审计、已执行、过期计划、无可信时区、未来时间、过时版本均拒绝；不修改动作方向、数量、价格或审计，也不生成订单。
- 写入口默认关闭。必须同时设置 `WORKBENCH_PERSISTED_READ_ENABLED=true`、`WORKBENCH_ACTION_DATE_WRITE_ENABLED=true`，并配置**至少 32 字符**随机 `WORKBENCH_ACTION_DATE_WRITE_TOKEN`；后端校验 Bearer 令牌，未配置或令牌不足长度则拒绝。仅在 HTTPS / 可信本地环境中启用，禁止在仓库提交令牌；前端只在表单内短暂持有，不写入 localStorage。
- `frontend/src/App.tsx`：中文日期表单位于已记录的「计划中」正式动作下，用户手工输入日期或清空；提交后重新读取只读总览，验证协议并更新今日/非今日分组。所有显示仍为 `executable=false`，不提供下单入口。
- `backend/tests/test_workbench_action_date.py`：默认关闭、短令牌、错误令牌、严格日期格式、时间戳并发冲突、已审计动作/过期计划等反例；`test_workbench_postgres_integration.py`：迁移后隔离 PostgreSQL 内经正式更新服务写入日期，再读取并验证分组，测试事务回滚。
- **验收边界**：此功能提供正式动作日期录入/保存/刷新路径，但真实用户身份认证、券商来源对账、正式动作创建/审计全流程和手机实机操作尚未验收。管理员令牌是有限的 opt-in 控制，不等于多用户授权系统；不能将此项判为整个 M8 Gate 通过。CI 以本次最新 HEAD 的实际运行结果为准。

- **本轮最新 CI 证据（HEAD `697467dc`）**：推送 [#40505288890](https://github.com/dgcary/structure-swing-workbench/actions/runs/40505288890) 与 PR [#40505295033](https://github.com/dgcary/structure-swing-workbench/actions/runs/40505295033) 均 completed/success；后端 426 passed、Ruff 通过、PostgreSQL 16/Alembic 迁移及正式日期写入往返通过，前端 89/89 测试与生产构建通过。此前中间提交的 TypeScript 回调遗漏、Ruff 导入排序、日期参数类型和时区引用失败已在本 HEAD 修复。CI 仅证明代码/合成数据测试通过，不代表真实账户或移动端实机通过。


### 2026-10-27 增量证据：正式动作日期写入的传输安全门禁

- `backend/app/main.py::_trusted_date_write_transport`：管理员 Bearer 令牌保护的日期修改接口**不再接受远程明文 HTTP**。仅接受 ASGI 已认证的 HTTPS scheme，或请求来源 IP 和目标主机均为回环地址的本机 HTTP；不信任客户端自行添加的 `X-Forwarded-Proto` 头。TLS 终止代理需正确、可信地向 ASGI 服务器传递 scheme；普通局域网 HTTP 页面不能执行管理员日期修改。
- `backend/tests/test_workbench_action_date.py::test_date_write_transport_requires_https_or_both_loopback_addresses` 和 `test_privileged_date_write_rejects_remote_http_even_with_valid_token`：验证 HTTPS/本机回环正例、远程 HTTP、伪造转发头及目标地址与来源不一致反例；原 Bearer 认证测试改为 HTTPS 测试客户端。
- **验收边界**：本项只防止管理员日期接口经远程明文传输令牌；不是完整用户登录、权限管理或实际 HTTPS 代理部署验收。全部动作仍不可执行，M8 Gate 仍 FAIL；真实账户/CSV、T 闭环/换仓/T+1、手机实机证据仍待补齐。CI 以本增量最新 HEAD 为准。
