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

const csvSamples: Record<string, string> = {
  account: "equity,available_cash,as_of\n1000000,500000,2026-11-18T10:00:00+08:00",
  holdings: "symbol,quantity,cost,as_of\n600000,10000,10.20,2026-11-18T10:00:00+08:00",
};

function CsvImportPanel({ onImported }: { onImported: () => void }) {
  const [kind, setKind] = useState("account");
  const [data, setData] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const result = await api.importCsv(kind, data);
      if (result.duplicate) {
        setMessage("CSV 内容与已导入记录一致，未重复导入");
      } else if (kind === "account") {
        setMessage("账户快照已导入");
      } else {
        setMessage(`持仓快照已导入 ${result.imported ?? 0} 批（权益未知，以快照锚定持仓）`);
      }
      setError(null);
      setData("");
      onImported();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setMessage(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="panel">
      <div className="panel-heading">
        <h2>账户 / 持仓 CSV 导入</h2>
        <span className="muted">m5 CSV 协议；相同内容重复导入自动去重。</span>
      </div>
      <form
        className="inline-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label>
          CSV 类型
          <select value={kind} onChange={(event) => setKind(event.target.value)}>
            <option value="account">账户快照（equity,available_cash,as_of）</option>
            <option value="holdings">持仓快照（symbol,quantity,cost,as_of）</option>
          </select>
        </label>
        <button type="button" className="ghost" onClick={() => setData(csvSamples[kind])}>
          填入示例
        </button>
        <button type="submit" disabled={busy || data.trim() === ""}>
          导入
        </button>
      </form>
      <textarea
        className="csv-input"
        rows={4}
        value={data}
        onChange={(event) => setData(event.target.value)}
        placeholder={csvSamples[kind]}
      />
      {message && <p className="notice">{message}</p>}
      {error && (
        <p role="alert" className="alert">
          导入失败：{error}
        </p>
      )}
    </div>
  );
}

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
                <span className="stat-value">
                  {overview.snapshot?.total_equity ?? (overview.snapshot ? "权益未知" : "未录入快照")}
                </span>
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
              <p className="muted">尚未录入账户快照；可在下方手工录入或从 CSV 导入。</p>
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
          <h3 className="sub-heading">当前持仓（快照 + 净成交）</h3>
          {!overview || overview.current_positions.length === 0 ? (
            <p className="muted">暂无持仓记录。</p>
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>证券</th>
                  <th>基准数量</th>
                  <th>净成交</th>
                  <th>当前数量</th>
                </tr>
              </thead>
              <tbody>
                {overview.current_positions.map((position) => (
                  <tr key={position.instrument_code}>
                    <td>
                      {position.instrument_name}（{position.instrument_code}）
                    </td>
                    <td>{position.baseline_quantity ?? "未知"}</td>
                    <td>{position.net_fill_delta ?? "—"}</td>
                    <td>{position.current_quantity ?? "未知"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </article>

        <article className="card">
          <h3>今日待执行动作</h3>
          <p className="muted">
            动作由计划生成并经纪律审计；在「交易计划」页创建动作、录入成交。
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

      <CsvImportPanel onImported={() => void load()} />
    </section>
  );
}
