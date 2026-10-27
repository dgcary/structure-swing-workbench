import { useEffect, useState } from "react";
import { PlanPreview } from "./PlanPreview";
import { AuditPreviewResult, type PartialAuditResult } from "./AuditPreviewResult";
import { CSVPreview } from "./CSVPreview";
import { KlinePreview } from "./KlinePreview";
import { AccountSnapshotPreview } from "./AccountSnapshotPreview";
import { TCyclePreview } from "./TCyclePreview";
import { LocalPlanDrafts } from "./LocalPlanDrafts";
import { LocalReview } from "./LocalReview";
import { summarizeLocalDrafts, type LocalDraftSummary } from "./localDraftSummary";
import { shouldRefreshLocalDrafts } from "./localDraftRefresh";
import { assertReadOnlyOverview } from "./overviewContract";

type Metric = {
  key: string;
  label: string;
  unit: string;
  value: string | null;
  status: "available" | "unavailable";
  source: string | null;
  as_of: string | null;
};

type Holding = {
  symbol: string;
  status: "snapshot" | "partial" | "unanchored" | "conflict";
  quantity: string | null;
  broker_display_cost: string | null;
  core_quantity: string | null;
  t_quantity: string | null;
  source: string | null;
  as_of: string | null;
  warning: string;
  applied_fill_ids?: string[];
  unanchored_fill_delta?: string | null;
};

type PersistedPlan = {
  id: string; symbol: string; name: string; version: number; state_zh: string;
  invalidation_price: string | null; first_target_price: string | null;
  initial_risk: string | null; current_risk: string | null;
  source: string; as_of: string | null; warning: string;
};

type PersistedAction = {
  id: string; symbol: string; action_zh: string; status_zh: string;
  planned_price_low: string | null; planned_price_high: string | null;
  planned_for_date: string | null; date_status: "today" | "other_day" | "unverified";
  source: string; as_of: string | null; executable: false; warning: string;
};

type PersistedAudit = {
  id: string; level: "pass" | "warning" | "overridable_fail" | "hard_fail";
  level_zh: string; summary: string; source: string; as_of: string | null;
  executable: false; warning: string;
};

type Overview = {
  schema_version: string;
  mode: "read_only" | "isolated_csv_preview";
  notice: string;
  metrics: Metric[];
  holdings: Holding[] | null;
  effective_plans: PersistedPlan[] | null;
  pending_actions: PersistedAction[] | null;
  audit_results: PersistedAudit[] | null;
  trade_execution_enabled: boolean;
};

type ResearchSection = {
  key: string;
  title: string;
  status: string;
  source_file: string | null;
  data: unknown;
  error: string | null;
};

type ResearchReport = {
  schema_version: string;
  generated_at: string;
  source: string;
  symbol: string | null;
  name: string | null;
  quality: string;
  sections: ResearchSection[];
};

const sections = [
  "总览", "计划管理", "审计结果", "K线", "成交导入", "T仓",
  "历史计划", "复盘", "研究样例",
] as const;
type Section = (typeof sections)[number];

const statusNames: Record<string, string> = {
  OK: "数据可用", NO_DATA: "暂无数据", SOURCE_ERROR: "来源异常",
  MISSING: "文件缺失", INVALID: "格式错误",
};

function Unavailable({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state" role="status">
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  );
}

function MetricCard({ metric }: { metric: Metric }) {
  const available = metric.status === "available" && metric.value !== null;
  return (
    <article className="metric-card">
      <h3>{metric.label}</h3>
      <div className="metric-value">
        {available ? <>{metric.value}<small>{metric.unit}</small></> : <span>未接入</span>}
      </div>
      <p className="metric-source">
        {available
          ? `来源：${metric.source ?? "未知"} · ${metric.as_of ?? "时间未知"}`
          : "尚无可验证的账户或业务事实"}
      </p>
    </article>
  );
}

function ActionDateEditor({
  action, onSaved,
}: { action: PersistedAction; onSaved: () => Promise<void> }) {
  const [plannedDate, setPlannedDate] = useState(action.planned_for_date ?? "");
  const [token, setToken] = useState("");
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState("");
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!action.as_of || !token) return;
    setPending(true);
    setMessage("");
    try {
      const response = await fetch(
        "/api/workbench/actions/" + encodeURIComponent(action.id) + "/planned-date",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
          body: JSON.stringify({
            planned_for_date: plannedDate || null,
            expected_as_of: action.as_of,
          }),
        },
      );
      if (!response.ok) {
        throw new Error(response.status === 409 ? "记录已改变或不允许修改，请刷新核对。" :
          response.status === 401 ? "管理员令牌无效。" :
          response.status === 404 ? "日期修改功能未启用或记录不存在。" :
          "保存失败（HTTP " + response.status + "）。");
      }
      const result: unknown = await response.json();
      if (typeof result !== "object" || result === null ||
          !("saved" in result) || result.saved !== true ||
          !("trade_execution_enabled" in result) ||
          result.trade_execution_enabled !== false) {
        throw new Error("日期保存响应不可信，请重新核对。");
      }
      setToken("");
      await onSaved();
      setMessage("人工日期已保存并重新读取；仍不可执行交易。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "日期保存失败。");
    } finally {
      setPending(false);
    }
  }
  return <details>
    <summary>人工修改正式动作日期（管理员授权）</summary>
    <p className="notice">仅修改计划中动作的日期，不改变交易内容或审计结论。默认关闭；需要管理员在后端显式启用。令牌仅在本次表单内使用，不保存到浏览器。</p>
    <form className="plan-form" onSubmit={save}>
      <label>人工指定计划日期（可留空清除）
        <input type="date" value={plannedDate}
          onChange={(event) => setPlannedDate(event.target.value)} />
      </label>
      <label>管理员令牌
        <input type="password" autoComplete="off" required value={token}
          onChange={(event) => setToken(event.target.value)} />
      </label>
      <button type="submit" disabled={pending}>{pending ? "保存中…" : "保存日期并刷新"}</button>
    </form>
    {message && <p role="status">{message}</p>}
  </details>;
}

function ActionCard({
  action, onSaved,
}: { action: PersistedAction; onSaved: () => Promise<void> }) {
  return (
    <article className="holding-card">
      <h3>{action.symbol} · {action.action_zh} · {action.status_zh}</h3>
      <p>计划价格：{action.planned_price_low ?? "未知"} ～ {action.planned_price_high ?? "未知"}</p>
      <p>人工计划日期：{action.planned_for_date ?? "未核实"} · {
        action.date_status === "today" ? "今日人工计划" :
        action.date_status === "other_day" ? "非今日计划" : "日期未核验"
      }</p>
      <p className="audit-unknown">仅供核对 · 不可执行</p>
      <p>来源：{action.source} · 数据时间：{action.as_of ?? "未核实"}</p>
      <p>{action.warning}</p>
      {action.status_zh === "计划中" && action.as_of !== null &&
        <ActionDateEditor key={action.as_of} action={action} onSaved={onSaved} />}
    </article>
  );
}

function ResearchDemo() {
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/research/sample")
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<ResearchReport>;
      })
      .then(setReport)
      .catch((reason: Error) => setError(reason.message));
  }, []);

  return (
    <section className="panel research-panel">
      <h2>研究资料（合成样例）</h2>
      <p className="notice">以下为固定合成数据，不是实时行情、真实账户或交易信号。</p>
      {!report && !error && <p>正在读取研究样例…</p>}
      {error && <p role="alert">研究样例读取失败：{error}</p>}
      {report && (
        <>
          <dl className="research-meta">
            <div><dt>标的</dt><dd>{report.name ?? "未知"}（{report.symbol ?? "未知"}）</dd></div>
            <div><dt>研究来源</dt><dd>{report.source}</dd></div>
            <div><dt>生成时间</dt><dd>{report.generated_at}</dd></div>
            <div><dt>数据版本</dt><dd>{report.schema_version}</dd></div>
            <div><dt>完整性</dt><dd>{report.quality === "OK" ? "样例完整" : "样例不完整"}</dd></div>
          </dl>
          <div className="research-grid">
            {report.sections.map((item) => (
              <article className="research-section" key={item.key}>
                <header><h3>{item.title}</h3><span>{statusNames[item.status] ?? "状态未知"}</span></header>
                <p>来源文件：{item.source_file ?? "未提供"}</p>
                {item.error && <p role="alert">{item.error}</p>}
                {item.data !== null && <pre>{JSON.stringify(item.data, null, 2)}</pre>}
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

export function App() {
  const [section, setSection] = useState<Section>("总览");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [baselineOverview, setBaselineOverview] = useState<Overview | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [backendStatus, setBackendStatus] = useState("连接中");
  const [lastAuditPreview, setLastAuditPreview] = useState<PartialAuditResult | null>(null);
  const [localDraftSummary, setLocalDraftSummary] = useState<LocalDraftSummary | null>(null);
  const [localDraftError, setLocalDraftError] = useState(false);
  useEffect(() => {
    if (section !== "总览") return;
    const refresh = () => {
      try {
        setLocalDraftSummary(summarizeLocalDrafts(localStorage));
        setLocalDraftError(false);
      } catch {
        setLocalDraftSummary(null);
        setLocalDraftError(true);
      }
    };
    refresh();
    const onStorage = (event: StorageEvent) => {
      if (event.storageArea === localStorage && shouldRefreshLocalDrafts(event.key)) {
        refresh();
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [section]);

  useEffect(() => {
    fetch("/api/health")
      .then((response) => {
        if (!response.ok) throw new Error("后端不可用");
        return response.json();
      })
      .then(() => setBackendStatus("后端已连接"))
      .catch(() => setBackendStatus("后端连接失败"));

    fetch("/api/workbench/overview")
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<Overview>;
      })
      .then((payload) => {
        assertReadOnlyOverview(payload, "read_only");
        setBaselineOverview(payload);
        setOverview((current) => current?.mode === "isolated_csv_preview" ? current : payload);
      })
      .catch((reason: Error) => setOverviewError(reason.message));
  }, []);

  async function refreshAfterDateEdit(): Promise<void> {
    const response = await fetch("/api/workbench/overview");
    if (!response.ok) throw new Error("重新读取正式动作失败，请刷新页面核对。");
    const payload: Overview = await response.json();
    assertReadOnlyOverview(payload, "read_only");
    setBaselineOverview(payload);
    setOverview((current) => current?.mode === "isolated_csv_preview" ? current : payload);
  }

  const todayActions = overview?.pending_actions?.filter(
    (action) => action.date_status === "today",
  ) ?? [];
  const otherActions = overview?.pending_actions?.filter(
    (action) => action.date_status !== "today",
  ) ?? [];

  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">STRUCTURE SWING · 个人交易体系</p>
          <h1>交易工作台</h1>
          <p className="subtitle">用户判断结构与交易，系统记录事实并审计纪律。</p>
        </div>
        <span className="connection-status">{backendStatus}</span>
      </header>

      <nav className="tabs" aria-label="工作台导航">
        {sections.map((item) => (
          <button
            key={item}
            type="button"
            className={section === item ? "tab active" : "tab"}
            aria-current={section === item ? "page" : undefined}
            onClick={() => setSection(item)}
          >
            {item}
          </button>
        ))}
      </nav>

      <main className="content">
        {section === "总览" && (
          <>
            <section className="alert-banner" role="status">
              <strong>{overview?.mode === "isolated_csv_preview" ? "本次上传 CSV · 临时预览" : "数据接入状态：未完成"}</strong>
              <p>{overview?.notice ?? "账户、持仓、计划与审计必须有可追溯来源；缺失值不会显示为零或通过。"}</p>
              {overviewError && <p role="alert">工作台接口异常：{overviewError}</p>}
            </section>
            <AccountSnapshotPreview
              onPreview={(snapshot) => { setOverview(snapshot); setOverviewError(null); }}
              onReset={() => { setOverview(baselineOverview); setOverviewError(null); }}
            />
            <div className="section-heading"><h2>账户与纪律总览</h2><span>{overview?.mode === "isolated_csv_preview" ? "上传 CSV · 非实时 · 未保存" : "只读 · 未连接券商"}</span></div>
            {overview ? (
              <section className="metric-grid" aria-label="账户指标">
                {overview.metrics.map((metric) => <MetricCard key={metric.key} metric={metric} />)}
              </section>
            ) : (
              <Unavailable title="账户指标暂不可用" detail="正在读取来源事实；连接失败时不展示模拟金额。" />
            )}
            <div className="two-column">
              <section className="panel">
                <h2>当前持仓与核心／T仓</h2>
                {overview?.holdings ? (
                  <div className="holding-list">
                    <p className="notice">仅展示已有来源的标的，不代表账户全量持仓。</p>
                    {overview.holdings.map((item) => (
                      <article className="holding-card" key={item.symbol}>
                        <h3>{item.symbol} · {{ conflict: "数据冲突", unanchored: "仅有成交记录", partial: "数量可追溯／成本待核", snapshot: "持仓快照" }[item.status]}</h3>
                        <p>持仓数量：{item.quantity ?? "未知"} · 券商显示成本：{item.broker_display_cost ?? "未知"}</p>
                        <p>核心仓：{item.core_quantity ?? "未核实"} · T仓：{item.t_quantity ?? "未核实"}</p>
                        {item.status === "unanchored" && (
                          <p role="status">已确认成交净变化：{item.unanchored_fill_delta ?? "未知"} 股；这是成交差额，<strong>不是当前持仓数量</strong>。</p>
                        )}
                        {(item.applied_fill_ids?.length ?? 0) > 0 && (
                          <p>关联成交：{item.applied_fill_ids?.length} 笔（仅当前来源范围内）</p>
                        )}
                        <p>来源：{item.source ?? "缺少来源"} · 数据时间：{item.as_of ?? "未知"}</p>
                        <p role="status">{item.warning}</p>
                      </article>
                    ))}
                  </div>
                ) : (
                  <Unavailable title="持仓数据未接入" detail="需要经核验的账户快照与成交记录；暂不推断空仓或仓位比例。" />
                )}
              </section>
              <section className="panel">
                <h2>有效交易计划</h2>
                {overview?.effective_plans && overview.effective_plans.length > 0 ? (
                  <div className="holding-list">
                    {overview.effective_plans.map((plan) => (
                      <article className="holding-card" key={plan.id}>
                        <h3>{plan.symbol} · {plan.name} · 第{plan.version}版</h3>
                        <p>计划状态：{plan.state_zh} · 结构失效价：{plan.invalidation_price ?? "未知"}</p>
                        <p>第一目标：{plan.first_target_price ?? "未知"} · 初始风险：{plan.initial_risk ?? "未核实"} · 当前风险：{plan.current_risk === null ? "未核实" : `${plan.current_risk} 元（核心仓历史估算）`}</p>
                        <p>来源：{plan.source} · 数据时间：{plan.as_of ?? "未核实"}</p>
                        <p className="notice">{plan.warning}</p>
                      </article>
                    ))}
                  </div>
                ) : <Unavailable title="正式有效计划未接入" detail="未读取到可追溯的正式有效计划；本机草稿不能替代正式计划。" />}
                <h3>本机人工计划草稿（未审计）</h3>
                {localDraftError ? <p role="alert">本机草稿读取异常，已停止展示；请核对原数据。</p> :
                  localDraftSummary && localDraftSummary.latest.length > 0 ? <>
                    <p className="notice">本机保存 {localDraftSummary.latest.length} 个计划、{localDraftSummary.versionCount} 个版本；均未审计，不可据此执行。</p>
                    {localDraftSummary.latest.slice(0, 3).map((draft) => <article className="draft-card" key={draft.id}>
                      <strong>{draft.symbol} · 第{draft.version}版 · 未审计</strong>
                      <p>人工分类：{draft.setup === "NONE" ? "未判断" : draft.setup} · 入场：{draft.entry} · 失效：{draft.stop} · 第一目标：{draft.target}</p>
                    </article>)}
                  </> : <p>本机暂无人工草稿；不代表没有正式持仓或计划。</p>}
                <button className="back-button" type="button" onClick={() => setSection("计划管理")}>查看本机草稿</button>
              </section>
              <section className="panel">
                <h2>今日人工计划动作（非交易指令）</h2>
                <p className="notice">仅将人工明确指定今日执行日期、且记录时间可核验的正式动作列在此处；仍需重新审计和券商核对，不代表可执行。</p>
                {todayActions.length > 0 ? (
                  <div className="holding-list">
                    {todayActions.map((action) => <ActionCard key={action.id} action={action} onSaved={refreshAfterDateEdit} />)}
                  </div>
                ) : <Unavailable title="今日计划动作尚未核实" detail="没有带可信人工日期的今日计划记录，不代表今天没有待处理事项。" />}
                <h3>其他已记录未完成动作（非今日待办）</h3>
                <p className="notice">未填写日期、日期不可信或计划日期不是今天的动作，不得冒充今日待办。</p>
                {otherActions.length > 0 ? (
                  <div className="holding-list">
                    {otherActions.map((action) => <ActionCard key={action.id} action={action} onSaved={refreshAfterDateEdit} />)}
                  </div>
                ) : <p>暂无其他可展示的历史动作；不代表已完成审计。</p>}
              </section>
              <section className="panel">
                <h2>纪律审计与可执行性</h2>
                <div className="audit-unknown">历史审计仅供查阅 · 不可认定可执行</div>
                {overview?.audit_results && overview.audit_results.length > 0 ? (
                  <>
                    {overview.audit_results.filter((audit) => audit.level !== "pass").map((audit) => (
                      <article className="holding-card" key={audit.id} role="status">
                        <strong>{audit.level_zh} · {audit.summary}</strong>
                        <p>来源：{audit.source} · 数据时间：{audit.as_of ?? "未核实"}</p>
                        <p>{audit.warning}</p>
                      </article>
                    ))}
                    {overview.audit_results.some((audit) => audit.level === "pass") && (
                      <details>
                        <summary>展开正常审计记录（{overview.audit_results.filter((audit) => audit.level === "pass").length}项）</summary>
                        {overview.audit_results.filter((audit) => audit.level === "pass").map((audit) => (
                          <article className="holding-card" key={audit.id}>
                            <strong>{audit.level_zh} · {audit.summary}</strong>
                            <p>来源：{audit.source} · 数据时间：{audit.as_of ?? "未核实"}</p>
                          </article>
                        ))}
                      </details>
                    )}
                  </>
                ) : <p>正式审计记录尚未接入。局部预审不构成交易许可。</p>}
                {lastAuditPreview && <p>最近一次局部预审：{lastAuditPreview.symbol} · {lastAuditPreview.highest_checked_level_zh}（不可执行）</p>}
                <button className="back-button" type="button" onClick={() => setSection("审计结果")}>查看审计状态</button>
              </section>
            </div>
          </>
        )}

        {section === "计划管理" && <><PlanPreview onResult={setLastAuditPreview} /><LocalPlanDrafts /></>}
        {section === "审计结果" && <section className="panel">
          <h2>纪律审计结果</h2>
          <div className="audit-unknown">正式审计未完成 · 不可执行</div>
          <p>当前仅提供手工输入字段的局部预审；未保存正式计划、未生成审计记录，也未授权交易。</p>
          {lastAuditPreview ? <>
            <AuditPreviewResult result={lastAuditPreview} />
            <button className="back-button" type="button" onClick={() => setLastAuditPreview(null)}>清除本次会话预审</button>
          </> : <Unavailable title="暂无本次会话预审结果" detail="请到计划管理填写计划字段并主动提交局部预审；没有结果不代表审计通过。" />}
          <button className="back-button" type="button" onClick={() => setSection("计划管理")}>前往计划管理</button>
        </section>}
        {section === "成交导入" && <CSVPreview />}
        {section === "K线" && <KlinePreview />}
        {section === "T仓" && <TCyclePreview />}
        {section === "历史计划" && <LocalPlanDrafts history />}
        {section === "复盘" && <LocalReview />}
        {section === "研究样例" && <ResearchDemo />}
        {section !== "总览" && section !== "研究样例" && section !== "计划管理" && section !== "审计结果" && section !== "成交导入" && section !== "K线" && section !== "T仓" && section !== "历史计划" && section !== "复盘" && (
          <section className="panel placeholder-panel">
            <h2>{section}</h2>
            <Unavailable
              title="此入口尚未连接持久化业务数据"
              detail="该模块将在 M8 后续开发中接入。当前不提供虚构行情、未审计交易动作或自动下单。"
            />
            <button className="back-button" type="button" onClick={() => setSection("总览")}>
              返回总览
            </button>
          </section>
        )}
      </main>
      <footer>仅供个人研究与纪律审计 · 不自动下单 · 不构成投资建议</footer>
    </div>
  );
}
