import { useCallback, useEffect, useState } from "react";
import type { ActionDto, PlanDto } from "../api";
import { api } from "../api";

const actionOptions: { value: string; side: string; label: string }[] = [
  { value: "initial_entry", side: "buy", label: "初始建仓（买入）" },
  { value: "confirmation_add", side: "buy", label: "确认加仓（买入）" },
  { value: "ordinary_add", side: "buy", label: "普通加仓（买入）" },
  { value: "positive_t_buyback", side: "buy", label: "正T买回（买入）" },
  { value: "reverse_t_buy", side: "buy", label: "反T先买（买入）" },
  { value: "positive_t_sell", side: "sell", label: "正T先卖（卖出）" },
  { value: "reverse_t_sell", side: "sell", label: "反T卖出（卖出）" },
  { value: "take_profit", side: "sell", label: "止盈（卖出）" },
  { value: "reduce", side: "sell", label: "减仓（卖出）" },
  { value: "stop_exit", side: "sell", label: "止损退出（卖出）" },
  { value: "exit_other", side: "sell", label: "其他退出（卖出）" },
];

const nowLocalIso = (): string => {
  const d = new Date();
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}+08:00`;
};

export function ExecutionPanel({
  plan,
  onChanged,
}: {
  plan: PlanDto;
  onChanged: () => void;
}) {
  const [actions, setActions] = useState<ActionDto[]>([]);
  const [actionType, setActionType] = useState("initial_entry");
  const [priceLow, setPriceLow] = useState("");
  const [priceHigh, setPriceHigh] = useState("");
  const [quantity, setQuantity] = useState("");
  const [cycleKey, setCycleKey] = useState("");
  const [note, setNote] = useState("");
  const [fillFor, setFillFor] = useState<string | null>(null);
  const [fillQty, setFillQty] = useState("");
  const [fillPrice, setFillPrice] = useState("");
  const [fillAt, setFillAt] = useState(nowLocalIso());
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const all = await api.listActions("");
    setActions(all.filter((item) => item.plan?.id === plan.id));
  }, [plan.id]);

  useEffect(() => {
    void load();
  }, [load]);

  const effectiveFacts = plan.versions?.find((v) => v.is_effective)?.facts ?? null;

  const run = async (action: () => Promise<string | void>) => {
    setBusy(true);
    try {
      const note = await action();
      if (note) setMessage(note);
      setError(null);
      await load();
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const selectedSide =
    actionOptions.find((option) => option.value === actionType)?.side ?? "buy";

  const createNewAction = () =>
    run(async () => {
      if (!plan.effective_version_id) return;
      const payload: Record<string, unknown> = {
        action_type: actionType,
        side: selectedSide,
        planned_price_low: priceLow.trim() === "" ? null : priceLow,
        planned_price_high: priceHigh.trim() === "" ? null : priceHigh,
        planned_quantity: quantity.trim() === "" ? null : quantity,
        t_cycle_key: cycleKey.trim() === "" ? null : cycleKey,
        user_note: note.trim() === "" ? null : note,
      };
      await api.createAction(plan.effective_version_id, payload);
      setPriceLow("");
      setPriceHigh("");
      setQuantity("");
      setCycleKey("");
      setNote("");
      return "执行动作已创建（计划中），可先审计再录入成交";
    });

  const submitFill = (actionId: string) =>
    run(async () => {
      const result = await api.recordFill(actionId, {
        quantity: fillQty,
        price: fillPrice,
        executed_at: fillAt,
      });
      setFillFor(null);
      setFillQty("");
      setFillPrice("");
      setFillAt(nowLocalIso());
      return `成交已录入：${result.audit_result.level?.label ?? ""}（${result.action.status?.label ?? ""}）`;
    });

  const isT = actionType.startsWith("positive_t") || actionType.startsWith("reverse_t");

  return (
    <div className="review-panel">
      <h3>执行动作与成交</h3>

      {plan.effective_version_id ? (
        <form
          className="inline-form"
          onSubmit={(event) => {
            event.preventDefault();
            void createNewAction();
          }}
        >
          <label>
            动作类型
            <select value={actionType} onChange={(event) => setActionType(event.target.value)}>
              {actionOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            计划价格下沿
            <input
              value={priceLow}
              onChange={(event) => setPriceLow(event.target.value)}
              placeholder={effectiveFacts?.initial_entry_price_low ?? "10.00"}
            />
          </label>
          <label>
            计划价格上沿
            <input
              value={priceHigh}
              onChange={(event) => setPriceHigh(event.target.value)}
              placeholder={effectiveFacts?.initial_entry_price_high ?? "10.50"}
            />
          </label>
          <label>
            计划数量
            <input
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              placeholder="股数"
            />
          </label>
          {isT && (
            <label>
              T 循环标识
              <input
                value={cycleKey}
                onChange={(event) => setCycleKey(event.target.value)}
                placeholder="T1"
              />
            </label>
          )}
          <button type="submit" disabled={busy}>
            创建动作
          </button>
        </form>
      ) : (
        <p className="muted">计划生效后才能创建执行动作（先完成审计决策）。</p>
      )}

      {message && <p className="notice">{message}</p>}
      {error && (
        <p role="alert" className="alert">
          {error}
        </p>
      )}

      {actions.length === 0 ? (
        <p className="muted">该计划还没有执行动作。</p>
      ) : (
        <div className="action-list">
          {actions.map((action) => (
            <div key={action.id} className="audit-item">
              <div className="audit-heading">
                <span>
                  {action.action_type?.label ?? "未知动作"}（{action.side?.label ?? "—"}）
                </span>
                <span className="badge">{action.status?.label ?? "未知状态"}</span>
              </div>
              <p className="muted">
                计划价 {action.planned_price_low ?? "—"}
                {action.planned_price_high ? ` ~ ${action.planned_price_high}` : ""}；数量{" "}
                {action.planned_quantity ?? "—"}
                {action.t_cycle_key ? `；T循环 ${action.t_cycle_key}` : ""}
              </p>
              {fillFor === action.id ? (
                <form
                  className="inline-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void submitFill(action.id);
                  }}
                >
                  <label>
                    成交数量
                    <input
                      required
                      value={fillQty}
                      onChange={(event) => setFillQty(event.target.value)}
                    />
                  </label>
                  <label>
                    成交价格
                    <input
                      required
                      value={fillPrice}
                      onChange={(event) => setFillPrice(event.target.value)}
                    />
                  </label>
                  <label>
                    成交时间
                    <input
                      required
                      value={fillAt}
                      onChange={(event) => setFillAt(event.target.value)}
                    />
                  </label>
                  <button type="submit" disabled={busy}>
                    确认录入
                  </button>
                  <button type="button" className="ghost" onClick={() => setFillFor(null)}>
                    取消
                  </button>
                </form>
              ) : (
                <div className="inline-form">
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => {
                      setFillFor(action.id);
                      setFillQty(action.planned_quantity ?? "");
                      setFillPrice(action.planned_price_low ?? "");
                      setFillAt(nowLocalIso());
                    }}
                    disabled={busy || action.status?.value === "filled" || action.status?.value === "cancelled"}
                  >
                    录入成交
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        const audit = await api.auditAction(action.id);
                        return `动作审计：${audit.level?.label ?? ""}`;
                      })
                    }
                  >
                    审计动作
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        await api.cancelAction(action.id);
                        return "动作已取消";
                      })
                    }
                  >
                    取消动作
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
