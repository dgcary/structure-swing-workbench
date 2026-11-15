# M8｜Web 工作台 REST API 与前端核心页面

## 目标与当前范围

本里程碑把已有领域服务接入 REST API 与 Web 工作台，形成"账户概览 → 计划管理 → 纪律审计 → 覆盖决策"的完整页面工作流。**不包含自动交易**：所有买卖决定仍由用户手工完成；动作创建与成交录入属于后续执行里程碑。

## API 一览

### 计划与审计（`backend/app/api/plans.py`）

- `POST /plans`：创建计划草稿（版本 1），`account_equity` 用于仓位金额换算。
- `GET /plans`：计划列表，支持 `status` 与 `active_only` 过滤。
- `GET /plans/{id}`：计划详情（全部版本 + 审计结果 + 覆盖记录）。
- `PATCH /plans/{id}/note`：更新非关键备注，不触发新版本。
- `POST /plans/{id}/revisions`：创建新版本（继承当前生效字段 + 变更项）。
- `POST /plans/{id}/close`：关闭计划。
- `POST /plan-versions/{id}/submit`：草稿提交审计。
- `POST /plan-versions/{id}/audit`：运行版本审计并持久化 `AuditResult`。
- `POST /plan-versions/{id}/decision`：审计决策（通过生效 / 拒绝 / 覆盖生效）。
- `GET /actions?status=planned`：只读动作列表（数据源："今日待执行动作"卡片）。

### 版本审计编排（`backend/app/services/plan_audit.py`）

纯函数服务，组合 M2 审计引擎规则，不触碰数据库与外部数据源：

- `plan_completeness`：正式计划必须有结构失效价与失效条件，缺失记可覆盖失败。
- `initial_position` / `confirmation_position` / `t_reserve_position`：40/30/30 仓位拆分。
- `single_trade_risk`：计划最大亏损 / 账户权益（按区间下沿与结构失效价计算，仓位金额按比例从权益换算）。
- `target_one`：第一目标减仓比例范围。

输入不全的规则**不会静默跳过**：每条跳过的规则以中文原因记录在审计结果的 `skipped_rules` 中。

### 审计决策语义

- 通过 / 警告 → 可直接激活。
- 可覆盖失败 → 必须用户确认 + 一句覆盖理由，生成 `ManualOverride` 永久记录，版本进入"带覆盖生效"。
- 硬性失败 → 不可覆盖，必须修改计划重新审计。

### 账户（`backend/app/api/account.py`）

- `POST /account/snapshots`：录入账户快照（总权益、可用现金、持仓明细、核心仓/T 仓分桶）。
- `GET /account/snapshots`：快照列表。
- `GET /account/overview`：首页概览（最新快照、有效计划、单笔风险、账户总风险）。

### 候选与行情

- `POST /candidates/screen`、`POST /candidates/screen-batch`：证据化候选筛选（必须提供证据，缺红线检查记待核实）。
- `GET /market/quote/{symbol}`、`GET /market/bars/{symbol}`、`GET /market/security/{symbol}`：懒加载 AKShare 适配器；可选依赖未安装时返回 503 与中文原因。

## 前端

单页工作台（React 19 + Vite），标签页导航，无新增运行时依赖：

- **概览**：账户风险概览（总权益 / 可用现金 / 持仓数 / 账户总风险）、当前持仓与有效计划、今日待执行动作（只读）。
- **交易计划**：计划列表、新建表单、版本详情（事实字段 + 审计结果 + 覆盖记录）、提交审计 / 运行审计 / 决策 / 覆盖 / 关闭。
- **候选筛选**：客观分类与重大风险人工核对表单，输出中文筛选结论。
- **行情与研究**：实时报价查询 + StockResearchPack 只读演示。

金额统一以 4 位小数字符串展示；业务术语全部中文。

## 安全与边界

- 审计引擎保持纯函数；API 层只做编排与持久化，不引入新的规则判断。
- 版本事实字段（趋势、Setup、反转确认等）只能来自用户显式输入，程序不推断。
- 覆盖必须留下理由与时间戳；硬性失败不可绕过。
- 行情为只读数据源；筛选与审计结果不生成买卖信号。

## 验证

- `backend/tests/test_api_plans.py`：计划生命周期、审计分级、硬性失败阻断、覆盖记录、版本与关闭。
- `backend/tests/test_plan_audit_service.py`：审计编排纯函数（风险边界 2%/3%、跳过规则、仓位换算）。
- `backend/tests/test_api_account.py`：快照录入、概览与单笔风险计算。
- `backend/tests/test_api_candidates.py`、`backend/tests/test_api_market.py`：候选筛选边界与注入假行情源。
- 后端 382 个测试全部通过，ruff 无告警；`tsc -b && vite build` 构建通过。

## 本地运行

```bash
# 后端（开发，SQLite 可用 DATABASE_URL 覆盖；生产用 docker compose）
cd backend && python -m venv .venv && .venv/Scripts/python -m pip install ".[dev]"
uvicorn app.main:app --port 8000

# 前端
cd frontend && npm install && npm run dev   # http://localhost:5173，/api 代理到后端

# 部署
docker compose up --build
```
