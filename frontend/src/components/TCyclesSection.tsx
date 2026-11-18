import { useCallback, useEffect, useState } from "react";
import type { TCycleDto } from "../api";
import { api } from "../api";

export function TCyclesSection({ backendReady }: { backendReady: boolean }) {
  const [cycles, setCycles] = useState<TCycleDto[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!backendReady) return;
    try {
      setCycles(await api.listTCycles(filter.trim() === "" ? null : filter.trim()));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [backendReady, filter]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="section">
      <div className="panel">
        <div className="panel-heading">
          <h2>T 仓循环</h2>
          <span className="muted">
            每只股票每天最多完成 2 个完整 T 循环；超额仅提示，用于纪律回顾。
          </span>
        </div>
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            void load();
          }}
        >
          <label>
            按证券代码筛选（可选）
            <input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="600000"
            />
          </label>
          <button type="button" className="ghost" onClick={() => void load()}>
            刷新
          </button>
        </form>
      </div>

      {error && (
        <p role="alert" className="alert">
          T 仓读取失败：{error}
        </p>
      )}

      {cycles.length === 0 ? (
        <div className="panel">
          <p>当前没有 T 仓循环；在「交易计划」页为 T 动作填写循环标识（t_cycle_key）后展示。</p>
        </div>
      ) : (
        <div className="panel">
          <table className="table">
            <thead>
              <tr>
                <th>证券</th>
                <th>循环</th>
                <th>交易日</th>
                <th>状态</th>
                <th>已配对数量</th>
                <th>毛盈亏</th>
                <th>剩余数量</th>
                <th>未平方向</th>
                <th>成交笔数</th>
              </tr>
            </thead>
            <tbody>
              {cycles.map((cycle) => (
                <tr key={`${cycle.instrument_code}-${cycle.t_cycle_key}`}>
                  <td>
                    {cycle.instrument_name}（{cycle.instrument_code}）
                  </td>
                  <td>{cycle.t_cycle_key}</td>
                  <td>{cycle.day}</td>
                  <td>
                    {cycle.status}
                    {cycle.exceeds_daily_limit && (
                      <span className="badge risk-warning">当日超限</span>
                    )}
                  </td>
                  <td>{cycle.matched_quantity ?? "—"}</td>
                  <td>{cycle.matched_gross_pnl ?? "—"}</td>
                  <td>{cycle.remaining_quantity ?? "—"}</td>
                  <td>{cycle.open_side?.label ?? "—"}</td>
                  <td>{cycle.fill_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
