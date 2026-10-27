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


### 2026-10-27 增量证据：已存在成交的正式动作禁止事后改写计划日期

- `backend/app/workbench/action_date.py`：即使旧动作状态仍标记「计划中」，只要该动作关联任意 `ExecutionFill`，管理员日期接口就返回 HTTP 409，拒绝事后修改人工计划日期；防止记录与实际成交日期发生混淆。已有动作审计的拒绝逻辑继续保留。
- `backend/tests/test_workbench_action_date.py`：增加状态仍为「计划中」但已有成交的反例，要求无数据库 flush、无日期变化。
- `backend/tests/test_workbench_postgres_integration.py`：在隔离 PostgreSQL 16/Alembic 数据库写入合成真实成交记录后，验证日期写入被拒绝且原日期未变。测试数据全部事务回滚。
- **验收边界**：这是历史成交不可改写的安全约束，不代表已完成真实券商/CSV 对账、T 闭环统计、换仓、T+1、含 T 仓风险或手机端实机验收；仍须以最新 HEAD 的 CI 结果核验。PR #19 保持 Draft、M8 Gate FAIL，禁止合并或启动 M9。


### 2026-10-27 增量证据：浏览器端管理员令牌传输保护

- `frontend/src/dateWriteTransport.ts` 与 `App.tsx`：日期表单在发出包含 Bearer 令牌的请求**之前**校验页面来源，远程 HTTP 页面直接拒绝发送；仅 HTTPS 页面或本机回环 HTTP 页面允许提交，避免服务端 HTTP 403 已发生但令牌仍先经明文网络泄露。
- `frontend/tests/dateWriteTransport.test.mjs`：覆盖 HTTPS、localhost/127.0.0.1/IPv6 回环、局域网明文、伪造本地域名和非 HTTP 协议。
- **验收边界**：该措施与后端传输门禁共同防护日期编辑令牌，不等于完成生产反向代理/TLS 部署、身份系统或移动端实机验收；全部交易动作仍不可执行。M8 Gate 仍 FAIL。


### 2026-10-27 增量证据：T 成交逐周期来源审查（不等于当日总次数）

- `backend/app/workbench/t_cycle_evidence.py`：读取数据库中正式 `TradeAction.t_cycle_key` 与 `ExecutionFill` 的**实际记录**，按证券/周期键关联正 T 先卖/买回、反 T 先买/卖出，聚合拆单成交；输出每周期 `closed/open/conflict`、开闭腿数量、成交来源及时间。计划草稿和未成交动作不能冒充成交。
- 反例：无周期键、方向与成交买卖不符、关闭数量超过开仓、闭腿早于开腿、同一时刻缺乏先后顺序、跨上海市场日期、未来/无时区时间戳、缺少成交来源均不能成为有效闭环。非完整周期只作为已记录的未闭环证据，不得计为已完成 T。
- `backend/app/workbench/persisted.py` → `overview.py`：在只读 API 附加 `t_cycle_evidence`。所有条目 `broker_reconciled=false`、`trade_execution_enabled=false`。**首页 `t_cycles_today` 与 `open_t_cycles` 仍为 unavailable**：M1 当前没有券商成交全量水位、清算确认或每日对账完成标记，不能以数据库部分记录声称完整日内次数，也不能以未录入视为零。
- 自动化证据：`backend/tests/test_workbench_t_cycle_evidence.py` 覆盖拆单、部分闭环、跨日、来源冲突、时间逆序和未来记录；`backend/tests/test_workbench_postgres_integration.py::test_postgres_recorded_t_cycle_fills_are_dated_but_not_broker_complete` 在迁移后 PostgreSQL 16 中核对实际成交记录往返、重复超额冲突与首页计数保持 unavailable。测试均使用合成数据和事务回滚，不代表真实券商账户已对账。
- **剩余 FAIL**：缺少完整券商成交来源/每日对账水位、日终未闭环正式转仓事实、日内换仓、T+1 可卖数量、含 T 仓风险、脱敏真实格式 CSV→PG 对账及移动 Safari/可信 TLS 实机证据；仍需独立审核。CI 以本轮最新 HEAD 实际运行结果为准。


### 2026-10-27 增量证据：跨计划版本 T 周期键隔离与缺键防碰撞

- `backend/app/workbench/t_cycle_evidence.py`：`t_cycle_key` 是人工标识，不保证全局唯一。现在正式成交按**证券 + 计划版本 ID + T 周期键**隔离；两个不同计划版本即使同证券、同键，也不得把一边的开仓成交与另一边的平仓成交拼成虚假的完整 T。返回 `plan_version_id` 供来源追溯。
- 对未填写周期键的成交使用结构化分组键，而不是拼接 `unkeyed:<成交ID>` 的伪键，避免真实用户周期键与内部标记意外重合；缺键仍视为冲突，不认证闭环。
- `backend/tests/test_workbench_t_cycle_evidence.py` 新增跨计划版本和伪键碰撞反例。**边界**：这仅改进已记录成交的逐周期证据，不证明券商全量成交、T 日终转仓、T+1 可卖量或首页总次数。未核实指标仍为 `unavailable`；M8 Gate 仍 FAIL。
- CI 结果以本次最新 HEAD 的 GitHub Actions 为准，不以此前绿色提交替代。


### 2026-10-27 增量证据：异常成交数量的只读投影安全防护

- `backend/app/workbench/t_cycle_evidence.py`：PostgreSQL NUMERIC 可能包含 `NaN` 等异常值。原实现虽然标记数量非法，仍将其参与 Decimal 累加和比较，可能触发 `InvalidOperation` 并导致整个总览接口失败。现在只允许**有限且大于零**的 Decimal 数量进入聚合与时间序列；其余数量一律标记 `conflict`，不认证 T 闭环。
- `backend/tests/test_workbench_t_cycle_evidence.py`：覆盖 NaN、正负无穷、负数、零数量，以及缺失成交来源的异常输入；验证不抛异常、不提供虚假数量和交易许可。
- 此修复属于已有 T 成交证据投影的可靠性修复，**不补齐**券商成交全量水位、日终转仓、日内换仓、T+1、含 T 仓风险或真实账户与移动端验收。M8 Gate 仍 FAIL，PR 保持 Draft；CI 须以最新 HEAD 实际结果为准。


### 2026-10-27 增量证据：T 成交价格完整性校验

- `backend/app/workbench/t_cycle_evidence.py`：正式成交数量即使平衡，若任一开腿或闭腿缺少成交价格、价格为零/负数或 PostgreSQL NUMERIC 的 `NaN`、正负无穷，也只能标记 `conflict`，不得认证为 `closed`。这属于已有成交证据的格式完整性校验，不计算盈利或自动判断买卖。
- `backend/tests/test_workbench_t_cycle_evidence.py::test_invalid_execution_price_never_certifies_a_completed_t_cycle`：覆盖两种成交方向的开/闭腿价格异常，确认不会发布已认证的数量或交易许可；原有有效价格测试保持覆盖正常正T/反T及拆单。
- **验收边界**：此项不能证明券商全量成交、日终未闭环转仓、日内换仓、T+1 可卖数量、含T仓账户风险、真实CSV→PostgreSQL对账或手机 Safari/TLS 实机验收。首页日内 T 总次数及未闭环总数仍保持 `unavailable`。独立 Gate 仍 FAIL，PR #19 保持 Draft；以最新 HEAD 的 GitHub Actions 为准。


### 2026-10-28 增量证据：重复券商成交编号不得认证 T 闭环

- `backend/app/workbench/t_cycle_evidence.py`：在按证券、计划版本和 T 周期键汇总之前，先全局核对已记录 T 成交的内部记录 ID 与（来源、外部成交编号）组合；重复的内部 ID 或相同来源下重复的外部成交编号，无论发生在同一周期还是不同计划版本，涉及的周期一律标记 `conflict`。不同来源的相同外部编号不直接视为冲突。缺少外部成交编号的手工记录仍不等于券商已对账。
- `backend/tests/test_workbench_t_cycle_evidence.py`：新增同周期重复外部编号、跨计划版本重复外部编号、重复内部成交 ID 反例，以及不同来源相同外部编号的正例；仍禁止发布日内完整 T 次数或交易许可。
- **验收边界**：仅修复已记录成交的去重可信度，不证明券商全量成交水位、日终 T 转仓、日内换仓、T+1 可卖量、含 T 仓风险、脱敏真实 CSV→PostgreSQL 对账或手机 Safari/可信 TLS 实机验收。首页完整 T 次数、未完成 T 总数仍为 `unavailable`；M8 整体 Gate 继续 FAIL，PR #19 保持 Draft，不合并、不部署、不启动 M9。CI 以最新 HEAD 的实际运行结果为准。


### 2026-10-28 增量证据：T 与普通动作之间的成交编号交叉核对

- **发现与修复**：原 `project_recorded_t_cycles` 仅查询 T 动作关联成交。若相同券商来源的外部成交编号同时出现在 T 成交与普通加仓/减仓成交中，原逻辑仍可能把 T 周期误判为 `closed`。现在只读查询全部正式动作成交，先跨动作类型检查内部成交 ID 与（来源、外部成交编号）重复，再仅投影 T 周期。普通动作不会被计为 T；与普通动作重复的 T 成交必须 `conflict`。
- **单元测试**：`backend/tests/test_workbench_t_cycle_evidence.py` 新增 T/普通动作同来源重复外部编号、跨动作重复内部 ID 的反例，以及不同来源相同外部编号不误判的正例。
- **隔离 PostgreSQL 实库测试**：`backend/tests/test_workbench_postgres_integration.py::test_postgres_recorded_t_cycle_fills_are_dated_but_not_broker_complete` 增加普通动作成交与 T 成交共享来源编号的数据库往返反例，必须使 T 周期冲突；测试事务回滚。
- **限制 / Gate FAIL**：跨动作去重仅验证**已记录**数据，不能保证券商全量成交、每日完整性水位、日终未闭环转普通加减仓、日内换仓、T+1 可卖数量、含 T 仓独立风险、脱敏真实券商 CSV→PG 对账或手机 Safari/可信 TLS 实机验收。首页 `t_cycles_today`、`open_t_cycles` 仍为 `unavailable`，不发布交易许可；PR #19 保持 Draft。CI 须核验本次最新 HEAD，旧绿灯不可代替。


### 2026-10-28 增量证据：日终未闭环 T 的只读待核验提示

- `backend/app/workbench/t_cycle_evidence.py`：对**同一市场日、方向/成交时间/数量/来源无冲突**且仍有剩余第一腿的已记录 T 周期，在上海市场当日 15:00 及之后或后续日期，标注 `end_of_day_unclosed=true`、`residual_quantity`、`ordinary_effect`（正 T 剩余为「普通减仓待核验」，反 T 剩余为「普通加仓待核验」）和 `requires_reaudit=true`。收盘前不标注；已闭环和冲突数据不标注。只读状态仍为 `open`，不得把它冒充已完成数据库状态迁移。
- `backend/tests/test_workbench_t_cycle_evidence.py::test_unclosed_t_at_day_end_only_exposes_unverified_ordinary_effect` 和 `test_closed_or_conflicting_t_never_claims_end_of_day_ordinary_conversion`：覆盖收盘前后、隔日、正反 T、部分闭环、已闭环与冲突反例，断言不启用交易。
- **验收结论：部分实现，M8 Gate 仍 FAIL。** 这只是已记录成交的日终复核线索，未证明券商成交全量、真实 T+1 可卖数量、自动持仓桶转移、主计划风险重审、持久化 BROKEN 状态及手机端展示；不得以此作为已完成转仓或交易授权。


### 2026-10-28 增量证据：已记录 T 周期中文页面与前端来源门禁

- `frontend/src/App.tsx`：在「T仓」页面新增正式数据库中**已记录成交的逐周期只读复核**。优先展示证据冲突，其次展示收盘未闭环及普通加减仓待核验提示，再展示未闭环与已记录买卖配对；明确交易日、周期键、第一/第二腿数量、剩余数量、成交来源条数及时间。仅称「已记录买卖配对（未对账）」，绝不称券商已完成核验。
- `frontend/src/overviewContract.ts`：严格校验周期状态、正/反 T、市场日期、数量与剩余量的**精确十进制守恒**、收盘待重审分类、成交来源、来源时间；强制 `broker_reconciled=false` 和 `trade_execution_enabled=false`。隔离 CSV 预览不得携带正式数据库 T 周期证据。
- `frontend/tests/tCycleEvidenceContract.test.mjs`：新增正常闭环、日终未闭环、数量/分类冲突、伪造券商已对账或交易许可、非法时间及 CSV 跨来源混入的协议反例。
- **CI 证据（代码 HEAD `df2f1c3d`）**：推送 [#40560916516](https://github.com/dgcary/structure-swing-workbench/actions/runs/40560916516) 和 PR [#40560921864](https://github.com/dgcary/structure-swing-workbench/actions/runs/40560921864) 均 completed/success；后端 453 passed、Ruff PASS、PostgreSQL 16/Alembic PASS，前端 TypeScript/Vite 构建及 94 项测试通过。文档提交后的最新 HEAD 须另行核验。
- **边界**：仅使已有的后端 T 成交证据可见并防止前端将其误当成交易许可。**首页当日 T 总次数与未完成 T 总数仍为 `unavailable`**，没有券商全量成交水位、日终持久化转仓、日内换仓、T+1 可卖数量、含 T 仓独立风险、真实 CSV→PG 对账或手机 Safari/TLS 实机证据。M8 Gate 仍 FAIL，PR #19 保持 Draft，不合并、不部署、不启动 M9。


### 2026-10-28 增量证据：已记录单票单日 T 次数超限的下界告警

- `backend/app/workbench/t_cycle_evidence.py`：对指定交易日、同一证券的**不同周期键/计划版本**，仅累计内部数量、方向、时间、成交编号均自洽的 `closed` 配对周期；若已记录的独立闭环至少 **3 个**，则该证券当日所有已记录周期输出 `recorded_daily_limit_alert=true` 与中文「疑似超限，必须人工复核」警示。拆单仍属于同一个周期，其他证券不合并计算；冲突或未闭环周期不被当成完整 T。
- **非认证语义**：少于 3 个时该字段为 `null`（未证明超限，**不是**合规通过）；即使超过 2 个也仅表示已记录配对的下界告警，不能证明券商全量成交已对账。首页 `t_cycles_today`、`open_t_cycles` 保持 `unavailable`，`broker_reconciled=false`、`trade_execution_enabled=false`；不写入交易状态、不修改主策略、不生成下单许可。
- `backend/tests/test_workbench_t_cycle_evidence.py`：3 个配对触发告警、2 个配对加冲突周期不误判、按证券隔离以及跨计划版本累计；`frontend/src/overviewContract.ts` 强制逐行标记与同证券/日期已记录闭环下界一致，拒绝伪造已合规/遗漏告警；`frontend/tests/tCycleEvidenceContract.test.mjs` 验证 3 个配对、缺失标记、伪造标记及跨证券反例。T 仓页面突出显示疑似超限。
- **Gate：增量待独立审核，M8 整体 FAIL。** 仍缺券商全量成交水位/逐日完整性、可信日终 BROKEN 转普通加减仓、日内换仓、T+1 可卖数量、CORE/T 独立成本与风险、脱敏真实 CSV→隔离 PostgreSQL 对账及移动 Safari/可信 TLS 实机验收。CI 以本轮最终 HEAD 的 Actions 结果为准，不把合成测试冒充真实账户证据。


### 2026-10-28 增量：隔离 CSV 每日成交清单与自报覆盖水位核对

- `backend/app/workbench/account_snapshot_preview.py` 在原有 **仅请求内存、无数据库写入** 的账户 CSV 预览中，增加可选 `daily_fill_claim`：交易日、导出时间、覆盖至时间、自报导出编号、自报逐笔成交编号及是否声明覆盖全天。必须同时提供成交 CSV；时间须带时区，覆盖时间不得晚于导出时间，不接受未来时间、重复/空白自报成交编号。
- 按 **上海交易日** 比对上传 CSV 与自报成交编号集合，输出缺失数、额外数、重复 CSV 行数；即使集合完全一致，也只返回 `matched_unverified`（自报清单一致、**未验证**），不会返回 broker verified。缺失、额外、重复行返回 `mismatch`；收盘前水位、无全天声明等返回 `insufficient`。无声明则 `daily_fill_coverage=null`，不能推断零成交。
- **重要证据边界**：用户可以同时编辑 CSV 和清单，因此“自报编号一致”不构成独立券商全量成交认证。接口仍 `persisted=false`、`realtime=false`、`full_account_verified=false`、`broker_reconciled=false`、`trade_execution_enabled=false`；首页当日 T 总次数和未完成 T 总数继续 `unavailable`，不允许据此执行日终正式转仓、T+1 或账户风险认证。
- `backend/tests/test_workbench_account_snapshot_preview.py` 新增匹配但不认证、缺失/额外编号、重复 CSV、收盘前水位、时区/重复声明/导出顺序/未来时间、缺少成交 CSV 及未声明情形的回归测试。
- **Gate：仅完成自报清单结构核对的第一步，M8 整体仍 FAIL。** 后续必须引入独立、可信的券商导出完整性证据（含账户身份、日期范围、来源真实性和可复核水位）、CSV→隔离 PostgreSQL 对账，才能考虑认证全量日内 T 统计与日终状态转换；还缺日内换仓、T+1、CORE/T 风险和手机 Safari/TLS 实机验收。


### 2026-10-28 增量证据：自报成交水位之外的迟到记录

- **状态：增量代码与自动测试已提交；M8 整体 FAIL。** `backend/app/workbench/account_snapshot_preview.py` 的隔离 CSV 每日清单核对新增 `outside_watermark_fill_count`。即使自报成交编号集合完全一致，只要同一上海市场交易日的任一成交时间**晚于**用户声明的 `complete_through`（按 UTC 绝对时间比较），就返回 `status=mismatch`，不再误标 `matched_unverified`。时间恰好等于水位不算越界。
- `backend/tests/test_workbench_account_snapshot_preview.py` 覆盖相同编号但迟于水位的 +08:00 / UTC 两种时区表示、边界时刻等价，以及来源未认证、交易禁止的断言。
- **证据边界**：此改动仅检查自报声明的内部时间一致性，不能证明券商独立导出身份、全量成交、逐日清算、真实账户 T+1 或正式 BROKEN 转仓。仍强制 `broker_reconciled=false`、`full_account_verified=false`、`trade_execution_enabled=false`；首页当日 T 次数与未闭环总数仍为 `unavailable`。独立 Gate 仍 FAIL，PR #19 保持 Draft；CI 以最新 HEAD 实际运行结果为准。


### 2026-10-28 增量证据：自报成交水位不得提前宣称已覆盖收盘

- `backend/app/workbench/account_snapshot_preview.py::_preview_daily_fill_coverage`：即使导出时间和覆盖水位处于允许的 5 分钟设备时钟偏差内，只要**实际当前时间尚未到达当日 15:00（上海时间）**，或导出/覆盖时间尚未真实发生，不能给出 `matched_unverified` 的完整交易日匹配标签；降为 `insufficient`。此限制只针对完整日声明，不改变既有未来时间过远时的 HTTP 422 拒绝。
- `backend/tests/test_workbench_account_snapshot_preview.py`：新增实际 14:58 与声明 15:00/15:01、实际 15:02 后可显示自报一致，以及实际 15:02 但导出 15:04 尚未发生的反例。状态仍不得变为 `broker_reconciled=true`，也不得授权交易。
- **验收边界**：自报编号匹配并不代表券商全量成交已证明，且没有真实账户/券商来源联调。仍需独立券商完整水位、T+1、日终正式转仓与重审、换仓、含 T 仓风险和移动端 Safari/TLS 实机。M8 Gate 仍 FAIL；PR #19 保持 Draft，禁止合并、部署或下发 M9。CI 必须核对本次最终 HEAD。
