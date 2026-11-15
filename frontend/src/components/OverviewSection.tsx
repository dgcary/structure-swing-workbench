import { useCallback, useEffect, useState } from "react";
import type { ActionDto, OverviewDto } from "../api";
import { api } from "../api";

const riskTone = (riskPct: string | null): string => {
  if (riskPct === null) return "risk-unknown";
  const risk = Number(riskPct);
  if (Number.isNaN(risk)) return "risk-unknown";
  if (risk <= 2) return "risk-pass";
  if (risk <= 3) return "risk-warning";
  return "risk-fail";
};

export function OverviewSection({ backendReady }: { backendReady: boolean }) {
  const [overview, setOverview] = useState<OverviewDto | null>(null);
  const [actions, setActions] = useState<ActionDto[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!backendReady) return;
    try {
      setOverview(await api.overview());
      setActions(await api.listActions("planned"));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [backendReady]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="section">
      {error && (
        <p role="alert" className="alert">
          概览读取失败：{error}
        </p>
      )}

      <div className="panel">
        <div className="panel-heading">
          <h2>账户风险概览</h2>
          <button type="button" className="ghost" onClick={() => void load()}>
            刷新
          </button>
        </div>
        {!overview && !error && <p>正在读取账户概览…</p>}
        {overview && (
          <>
            <div className="stat-row">
              <div className="stat">
                <span className="stat-label">账户总权益</span>
                <span className="stat-value">{overview.snapshot?.total_equity ?? "未录入快照"}</span>
              </div>
              <div className="stat">
                <span className="stat-label">可用现金</span>
                <span className="stat-value">{overview.snapshot?.available_cash ?? "—"}</span>
              </div>
              <div className="stat">
                <span className="stat-label">持仓数量</span>
                <span className="stat-value">{overview.position_count}</span>
              </div>
              <div className={`stat ${riskTone(overview.total_risk_pct)}`}>
                <span className="stat-label">账户总风险</span>
                <span className="stat-value">
                  {overview.total_risk_pct === null ? "—" : `${overview.total_risk_pct}%`}
                </span>
              </div>
            </div>
            {overview.snapshot && (
              <p className="muted">快照时间：{overview.snapshot.captured_at}（来源：{overview.snapshot.source}）</p>
            )}
            {!overview.snapshot && (
              <p className="muted">尚未录入账户快照；先在下方录入或等待 CSV 导入功能。</p>
            )}
          </>
        )}
      </div>

      <div className="grid">
        <article className="card">
          <h3>当前持仓与有效计划</h3>
          {!overview || overview.active_plans.length === 0 ? (
            <p>当前没有有效主计划。</p>
          ) : (
            <ul className="plain-list">
              {overview.active_plans.map((plan) => (
                <li key={plan.id}>
                  <strong>{plan.instrument_name}</strong>（{plan.instrument_code}）
                  <span className={`badge ${riskTone(plan.risk_pct)}`}>
                    单笔风险：{plan.risk_pct === null ? "数据不全" : `${plan.risk_pct}%`}
                  </span>
                  <span className="badge">{plan.status?.label ?? "未知状态"}</span>
                </li>
              ))}
            </ul>
          )}
          {!overview || overview.snapshot === null || overview.snapshot.positions.length === 0 ? (
            <p className="muted">暂无持仓快照明细。</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>证券</th>
                  <th>数量</th>
                  <th>市值</th>
                  <th>券商成本</th>
                </tr>
              </thead>
              <tbody>
                {overview.snapshot.positions.map((position) => (
                  <tr key={position.instrument_code}>
                    <td>
                      {position.instrument_name}（{position.instrument_code}）
                    </td>
                    <td>{position.total_quantity ?? "—"}</td>
                    <td>{position.market_value ?? "—"}</td>
                    <td>{position.broker_cost_price ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </article>

        <article className="card">
          <h3>今日待执行动作</h3>
          <p className="muted">
            动作由计划生成并经纪律审计；动作创建与成交录入将在执行里程碑提供，当前为只读展示。
          </p>
          {actions.length === 0 ? (
            <p>当前没有待执行动作。</p>
          ) : (
            <ul className="plain-list">
              {actions.map((action) => (
                <li key={action.id}>
                  {action.plan
                    ? `${action.plan.instrument_name}（${action.plan.instrument_code}）`
                    : "未知计划"}
                  ：{action.action_type?.label ?? "未知动作"}（{action.side?.label ?? "—"}）
                  <span className="badge">{action.status?.label ?? "未知状态"}</span>
                </li>
              ))}
            </ul>
          )}
        </article>
      </div>
    </section>
  );
}
