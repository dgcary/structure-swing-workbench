import { useEffect, useState } from "react";
import { CandidatesSection } from "./components/CandidatesSection";
import { MarketSection } from "./components/MarketSection";
import { OverviewSection } from "./components/OverviewSection";
import { PlansSection } from "./components/PlansSection";
import { TCyclesSection } from "./components/TCyclesSection";
import { api } from "./api";

type TabKey = "overview" | "plans" | "tcycles" | "candidates" | "market";

const tabs: { key: TabKey; label: string }[] = [
  { key: "overview", label: "概览" },
  { key: "plans", label: "交易计划" },
  { key: "tcycles", label: "T 仓" },
  { key: "candidates", label: "候选筛选" },
  { key: "market", label: "行情与研究" },
];

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

const sectionStatusNames: Record<string, string> = {
  OK: "数据可用",
  NO_DATA: "暂无数据",
  SOURCE_ERROR: "来源异常",
  MISSING: "文件缺失",
  INVALID: "格式错误",
};

function ResearchPanel() {
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/research/sample")
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json();
      })
      .then((data: ResearchReport) => setReport(data))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <div className="panel research-panel" aria-label="研究资料演示">
      <p className="eyebrow">M6 · StockResearchPack</p>
      <h2>研究资料（只读演示）</h2>
      <p className="research-notice">
        当前展示固定合成样例，不是真实行情、投资建议或交易信号；不自动下单。
      </p>
      {!report && !error && <p>正在读取研究样例…</p>}
      {error && (
        <p role="alert">研究样例读取失败：{error}</p>
      )}
      {report && (
        <>
          <dl className="research-meta">
            <div><dt>标的</dt><dd>{report.name ?? "未知"}（{report.symbol ?? "未知"}）</dd></div>
            <div><dt>研究来源</dt><dd>{report.source}</dd></div>
            <div><dt>研究时间</dt><dd>{report.generated_at}</dd></div>
            <div><dt>数据版本</dt><dd>{report.schema_version}</dd></div>
            <div><dt>完整性</dt><dd>{report.quality === "OK" ? "完整" : "部分数据缺失或异常"}</dd></div>
          </dl>
          <div className="research-grid">
            {report.sections.map((section) => (
              <article className="research-section" key={section.key}>
                <div className="research-heading">
                  <h3>{section.title}</h3>
                  <span className={`status status-${section.status.toLowerCase()}`}>
                    {sectionStatusNames[section.status] ?? "未知状态"}
                  </span>
                </div>
                <p className="research-path">来源文件：{section.source_file ?? "未提供"}</p>
                {section.error && <p role="alert">{section.error}</p>}
                {section.data !== null && <pre>{JSON.stringify(section.data, null, 2)}</pre>}
                {section.data === null && !section.error && <p>无可展示的研究内容。</p>}
              </article>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export function App() {
  const [tab, setTab] = useState<TabKey>("overview");
  const [backendReady, setBackendReady] = useState(false);
  const [environment, setEnvironment] = useState<string | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  useEffect(() => {
    api
      .health()
      .then((health) => {
        setBackendReady(true);
        setEnvironment(health.environment);
        setHealthError(null);
      })
      .catch((err: Error) => setHealthError(err.message));
  }, []);

  return (
    <main className="page">
      <section className="hero">
        <p className="eyebrow">Structure Swing v1</p>
        <h1>交易工作台</h1>
        <p className="subtitle">AI 筛候选，用户做判断，程序守纪律。</p>
        <p className="muted">
          {healthError
            ? `后端连接失败：${healthError}`
            : backendReady
              ? `后端状态：正常（${environment}）`
              : "正在连接后端…"}
        </p>
      </section>

      <nav className="tabs" aria-label="工作台导航">
        {tabs.map((item) => (
          <button
            key={item.key}
            type="button"
            className={`tab ${tab === item.key ? "active" : ""}`}
            onClick={() => setTab(item.key)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {tab === "overview" && <OverviewSection backendReady={backendReady} />}
      {tab === "plans" && <PlansSection backendReady={backendReady} />}
      {tab === "tcycles" && <TCyclesSection backendReady={backendReady} />}
      {tab === "candidates" && <CandidatesSection backendReady={backendReady} />}
      {tab === "market" && (
        <>
          <MarketSection backendReady={backendReady} />
          <ResearchPanel />
        </>
      )}
    </main>
  );
}
