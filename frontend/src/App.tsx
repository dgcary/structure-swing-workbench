import { useEffect, useState } from "react";
import { PlanPreview } from "./PlanPreview";
import { CSVPreview } from "./CSVPreview";
import { KlinePreview } from "./KlinePreview";

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
};

type Overview = {
  schema_version: string;
  mode: "read_only";
  notice: string;
  metrics: Metric[];
  holdings: Holding[] | null;
  effective_plans: unknown[] | null;
  pending_actions: unknown[] | null;
  audit_results: unknown[] | null;
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
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [backendStatus, setBackendStatus] = useState("连接中");

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
        if (payload.schema_version !== "m8.overview.v1" || payload.mode !== "read_only") {
          throw new Error("工作台数据协议不匹配");
        }
        setOverview(payload);
      })
      .catch((reason: Error) => setOverviewError(reason.message));
  }, []);

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
              <strong>数据接入状态：未完成</strong>
              <p>{overview?.notice ?? "账户、持仓、计划与审计必须有可追溯来源；缺失值不会显示为零或通过。"}</p>
              {overviewError && <p role="alert">工作台接口异常：{overviewError}</p>}
            </section>
            <div className="section-heading"><h2>账户与纪律总览</h2><span>只读 · 未连接券商</span></div>
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
                        <h3>{item.symbol} · {item.status === "conflict" ? "数据冲突" : "部分持仓事实"}</h3>
                        <p>持仓数量：{item.quantity ?? "未知"} · 券商显示成本：{item.broker_display_cost ?? "未知"}</p>
                        <p>核心仓：{item.core_quantity ?? "未核实"} · T仓：{item.t_quantity ?? "未核实"}</p>
                        <p>来源：{item.source ?? "缺少持仓基准"} · {item.as_of ?? "基准时间未知"}</p>
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
                <Unavailable title="计划数据未接入" detail="结构失效价、第一目标、初始／当前风险及计划状态待持久化服务接入。" />
              </section>
              <section className="panel">
                <h2>今日待执行动作</h2>
                <Unavailable title="尚无可验证的待办" detail="待办只能来自用户制定且经过审计的计划；此处不会生成买卖建议。" />
              </section>
              <section className="panel">
                <h2>纪律审计与可执行性</h2>
                <div className="audit-unknown">未审计 · 不可认定可执行</div>
                <p>硬性失败与可覆盖失败将在接入审计记录后优先展示；普通通过项默认折叠。</p>
              </section>
            </div>
          </>
        )}

        {section === "计划管理" && <PlanPreview />}
        {section === "成交导入" && <CSVPreview />}
        {section === "K线" && <KlinePreview />}
        {section === "研究样例" && <ResearchDemo />}
        {section !== "总览" && section !== "研究样例" && section !== "计划管理" && section !== "成交导入" && section !== "K线" && (
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
