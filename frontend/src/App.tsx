import { useEffect, useState } from "react";

type Health = {
  status: string;
  service: string;
  environment: string;
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

const statusNames: Record<string, string> = {
  OK: "数据可用",
  NO_DATA: "暂无数据",
  SOURCE_ERROR: "来源异常",
  MISSING: "文件缺失",
  INVALID: "格式错误",
};

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [researchError, setResearchError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      })
      .then(setHealth)
      .catch((err: Error) => setError(err.message));

    fetch("/api/research/sample")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      })
      .then((data: ResearchReport) => setReport(data))
      .catch((err: Error) => setResearchError(err.message));
  }, []);

  return (
    <main className="page">
      <section className="hero">
        <p className="eyebrow">Structure Swing v1</p>
        <h1>交易工作台</h1>
        <p className="subtitle">AI 筛候选，用户做判断，程序守纪律。</p>
      </section>

      <section className="panel">
        <h2>系统状态</h2>
        {health && <p>后端状态：正常（{health.environment}）</p>}
        {!health && !error && <p>正在连接后端…</p>}
        {error && <p>后端连接失败：{error}</p>}
      </section>

      <section className="grid">
        <article className="card">
          <h3>账户风险概览</h3>
          <p>账户事实层已具备，待工作台接入。</p>
        </article>
        <article className="card">
          <h3>当前持仓与有效计划</h3>
          <p>持仓与计划领域模型已具备，待界面接入。</p>
        </article>
        <article className="card">
          <h3>今日待执行动作</h3>
          <p>待执行动作需由用户制定并经纪律审计。</p>
        </article>
      </section>

      <section className="panel research-panel" aria-label="研究资料演示">
        <p className="eyebrow">M6 · StockResearchPack</p>
        <h2>研究资料（只读演示）</h2>
        <p className="research-notice">
          当前展示固定合成样例，不是真实行情、投资建议或交易信号；不自动下单。
        </p>
        {!report && !researchError && <p>正在读取研究样例…</p>}
        {researchError && <p role="alert">研究样例读取失败：{researchError}</p>}
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
                      {statusNames[section.status] ?? "未知状态"}
                    </span>
                  </div>
                  <p className="research-path">来源文件：{section.source_file ?? "未提供"}</p>
                  {section.error && <p role="alert">{section.error}</p>}
                  {section.data !== null && (
                    <pre>{JSON.stringify(section.data, null, 2)}</pre>
                  )}
                  {section.data === null && !section.error && <p>无可展示的研究内容。</p>}
                </article>
              ))}
            </div>
          </>
        )}
      </section>
    </main>
  );
}
