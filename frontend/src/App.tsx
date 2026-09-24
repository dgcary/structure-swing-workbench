import { useEffect, useState } from "react";

type Health = {
  status: string;
  service: string;
  environment: string;
};

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

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
          <p>等待 M1 / M2 接入账户、持仓和审计模型。</p>
        </article>
        <article className="card">
          <h3>当前持仓与有效计划</h3>
          <p>等待领域模型接入。</p>
        </article>
        <article className="card">
          <h3>今日待执行动作</h3>
          <p>等待动作与审计引擎接入。</p>
        </article>
      </section>
    </main>
  );
}
