import { useCallback, useEffect, useState } from "react";
import type { PlanDto } from "../api";
import { api } from "../api";

const levelTone: Record<string, string> = {
  pass: "risk-pass",
  warning: "risk-warning",
  overridable_fail: "risk-overridable",
  hard_fail: "risk-fail",
};

const stateNames: Record<string, string> = {
  draft: "草稿",
  pending_audit: "待审计",
  effective: "生效",
  effective_with_override: "带覆盖生效",
  superseded: "已被替代",
  rejected: "已拒绝",
  closed: "已关闭",
};

type PlanForm = {
  instrument_code: string;
  instrument_name: string;
  setup_type: string;
  structure_stage: string;
  entry_mode: string;
  planned_total_position_pct: string;
  initial_entry_price_low: string;
  initial_entry_price_high: string;
  initial_entry_pct: string;
  confirmation_add_pct: string;
  t_reserve_pct: string;
  structure_invalidation_price: string;
  structure_invalidation_condition: string;
  first_target_price: string;
  first_target_type: string;
  first_target_reduce_pct: string;
  account_equity: string;
};

const emptyForm: PlanForm = {
  instrument_code: "",
  instrument_name: "",
  setup_type: "c",
  structure_stage: "early",
  entry_mode: "price_range",
  planned_total_position_pct: "30",
  initial_entry_price_low: "",
  initial_entry_price_high: "",
  initial_entry_pct: "40",
  confirmation_add_pct: "30",
  t_reserve_pct: "30",
  structure_invalidation_price: "",
  structure_invalidation_condition: "",
  first_target_price: "",
  first_target_type: "prior_high",
  first_target_reduce_pct: "50",
  account_equity: "",
};

const numberOrNull = (value: string): string | null => (value.trim() === "" ? null : value);

function buildVersionPayload(form: PlanForm): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    setup_type: form.setup_type,
    structure_stage: form.structure_stage,
    entry_mode: form.entry_mode,
    planned_total_position_pct: numberOrNull(form.planned_total_position_pct),
    initial_entry_price_low: numberOrNull(form.initial_entry_price_low),
    initial_entry_pct: numberOrNull(form.initial_entry_pct),
    confirmation_add_pct: numberOrNull(form.confirmation_add_pct),
    t_reserve_pct: numberOrNull(form.t_reserve_pct),
    structure_invalidation_price: numberOrNull(form.structure_invalidation_price),
    structure_invalidation_condition: numberOrNull(form.structure_invalidation_condition),
    first_target_price: numberOrNull(form.first_target_price),
    first_target_type: form.first_target_type,
    first_target_reduce_pct: numberOrNull(form.first_target_reduce_pct),
  };
  if (form.entry_mode === "price_range") {
    payload.initial_entry_price_high = numberOrNull(form.initial_entry_price_high);
  }
  return Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== null));
}

export function PlansSection({ backendReady }: { backendReady: boolean }) {
  const [plans, setPlans] = useState<PlanDto[]>([]);
  const [selected, setSelected] = useState<PlanDto | null>(null);
  const [form, setForm] = useState<PlanForm>(emptyForm);
  const [showForm, setShowForm] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [auditEquity, setAuditEquity] = useState("");
  const [overrideReason, setOverrideReason] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!backendReady) return;
    try {
      const listing = await api.listPlans(false);
      setPlans(listing);
      setError(null);
      setSelected((current) =>
        current ? (listing.find((item) => item.id === current.id) ?? current) : current,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [backendReady]);

  useEffect(() => {
    void load();
  }, [load]);

  const openDetail = async (planId: string) => {
    try {
      setSelected(await api.getPlan(planId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const run = async (action: () => Promise<string | void>) => {
    setBusy(true);
    try {
      const note = await action();
      if (note) setMessage(note);
      setError(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const submitPlanForm = () =>
    run(async () => {
      const created = await api.createPlan({
        instrument_code: form.instrument_code.trim(),
        instrument_name: form.instrument_name.trim(),
        account_equity: numberOrNull(form.account_equity),
        version: buildVersionPayload(form),
      });
      setForm(emptyForm);
      setShowForm(false);
      await openDetail(created.id);
      return "计划草稿已创建";
    });

  const effectiveVersion = selected?.versions?.find((version) => version.is_effective) ?? null;
  const pendingVersion =
    selected?.versions?.find((version) => version.state?.value === "pending_audit") ?? null;
  const draftVersion =
    selected?.versions?.find((version) => version.state?.value === "draft") ?? null;
  const actionable = pendingVersion ?? draftVersion ?? effectiveVersion;
  const audits = actionable?.audit_results ?? [];
  const latestAudit = audits[0] ?? null;

  return (
    <section className="section">
      {error && (
        <p role="alert" className="alert">
          {error}
        </p>
      )}
      {message && <p className="notice">{message}</p>}

      <div className="panel">
        <div className="panel-heading">
          <h2>交易计划</h2>
          <button type="button" className="ghost" onClick={() => setShowForm((value) => !value)}>
            {showForm ? "收起新建表单" : "新建计划"}
          </button>
        </div>

        {showForm && (
          <form
            className="plan-form"
            onSubmit={(event) => {
              event.preventDefault();
              void submitPlanForm();
            }}
          >
            <div className="form-row">
              <label>
                证券代码
                <input
                  required
                  value={form.instrument_code}
                  onChange={(event) => setForm({ ...form, instrument_code: event.target.value })}
                  placeholder="600000"
                />
              </label>
              <label>
                证券名称
                <input
                  required
                  value={form.instrument_name}
                  onChange={(event) => setForm({ ...form, instrument_name: event.target.value })}
                  placeholder="浦发银行"
                />
              </label>
              <label>
                Setup 类型
                <select
                  value={form.setup_type}
                  onChange={(event) => setForm({ ...form, setup_type: event.target.value })}
                >
                  <option value="c">C｜上升趋势早中段回踩</option>
                  <option value="a">A｜横盘区间下沿</option>
                  <option value="b">B｜深回撤反转</option>
                </select>
              </label>
              <label>
                结构阶段
                <select
                  value={form.structure_stage}
                  onChange={(event) => setForm({ ...form, structure_stage: event.target.value })}
                >
                  <option value="early">早段</option>
                  <option value="middle">中段</option>
                  <option value="late">后段</option>
                </select>
              </label>
            </div>
            <div className="form-row">
              <label>
                建仓方式
                <select
                  value={form.entry_mode}
                  onChange={(event) => setForm({ ...form, entry_mode: event.target.value })}
                >
                  <option value="price_range">价格区间</option>
                  <option value="single_price">单一价格</option>
                </select>
              </label>
              <label>
                计划买入下沿
                <input
                  required
                  value={form.initial_entry_price_low}
                  onChange={(event) =>
                    setForm({ ...form, initial_entry_price_low: event.target.value })
                  }
                  placeholder="10.00"
                />
              </label>
              {form.entry_mode === "price_range" && (
                <label>
                  计划买入上沿
                  <input
                    value={form.initial_entry_price_high}
                    onChange={(event) =>
                      setForm({ ...form, initial_entry_price_high: event.target.value })
                    }
                    placeholder="10.50"
                  />
                </label>
              )}
              <label>
                账户总权益（用于换算）
                <input
                  value={form.account_equity}
                  onChange={(event) => setForm({ ...form, account_equity: event.target.value })}
                  placeholder="1000000"
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                计划总仓位 %
                <input
                  value={form.planned_total_position_pct}
                  onChange={(event) =>
                    setForm({ ...form, planned_total_position_pct: event.target.value })
                  }
                />
              </label>
              <label>
                初始建仓 %
                <input
                  value={form.initial_entry_pct}
                  onChange={(event) => setForm({ ...form, initial_entry_pct: event.target.value })}
                />
              </label>
              <label>
                确认加仓 %
                <input
                  value={form.confirmation_add_pct}
                  onChange={(event) =>
                    setForm({ ...form, confirmation_add_pct: event.target.value })
                  }
                />
              </label>
              <label>
                T 仓 %
                <input
                  value={form.t_reserve_pct}
                  onChange={(event) => setForm({ ...form, t_reserve_pct: event.target.value })}
                />
              </label>
            </div>
            <div className="form-row">
              <label>
                结构失效价
                <input
                  value={form.structure_invalidation_price}
                  onChange={(event) =>
                    setForm({ ...form, structure_invalidation_price: event.target.value })
                  }
                  placeholder="9.60"
                />
              </label>
              <label>
                结构失效条件
                <input
                  value={form.structure_invalidation_condition}
                  onChange={(event) =>
                    setForm({ ...form, structure_invalidation_condition: event.target.value })
                  }
                  placeholder="收盘跌破9.60视为结构失效"
                />
              </label>
              <label>
                第一目标价
                <input
                  value={form.first_target_price}
                  onChange={(event) => setForm({ ...form, first_target_price: event.target.value })}
                  placeholder="11.50"
                />
              </label>
              <label>
                第一目标减仓 %
                <input
                  value={form.first_target_reduce_pct}
                  onChange={(event) =>
                    setForm({ ...form, first_target_reduce_pct: event.target.value })
                  }
                />
              </label>
            </div>
            <button type="submit" disabled={busy}>
              创建计划草稿
            </button>
          </form>
        )}

        {plans.length === 0 ? (
          <p>还没有交易计划；点击「新建计划」创建第一份草稿。</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>证券</th>
                <th>状态</th>
                <th>备注</th>
                <th>创建时间</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {plans.map((plan) => (
                <tr key={plan.id} className={selected?.id === plan.id ? "selected-row" : undefined}>
                  <td>
                    {plan.instrument_name}（{plan.instrument_code}）
                  </td>
                  <td>{plan.status?.label ?? "未知"}</td>
                  <td>{plan.user_note ?? "—"}</td>
                  <td>{plan.created_at ?? "—"}</td>
                  <td>
                    <button type="button" className="ghost" onClick={() => void openDetail(plan.id)}>
                      详情
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <div className="panel">
          <div className="panel-heading">
            <h2>
              {selected.instrument_name}（{selected.instrument_code}）计划详情
            </h2>
            <span className="badge">{selected.status?.label ?? "未知状态"}</span>
          </div>

          <div className="version-list">
            {selected.versions?.map((version) => (
              <article key={version.id} className={`version-card ${version.is_effective ? "effective" : ""}`}>
                <div className="version-heading">
                  <h3>
                    版本 v{version.version_number}
                    {version.is_effective ? "（生效）" : `（${stateNames[version.state?.value ?? ""] ?? "未知"}）`}
                  </h3>
                  <span className="muted">{version.created_at}</span>
                </div>
                <dl className="facts">
                  <div>
                    <dt>Setup</dt>
                    <dd>{version.facts.setup_type?.label ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>建仓方式</dt>
                    <dd>{version.facts.entry_mode?.label ?? "—"}</dd>
                  </div>
                  <div>
                    <dt>计划买入</dt>
                    <dd>
                      {version.facts.initial_entry_price_low ?? "—"}
                      {version.facts.initial_entry_price_high
                        ? ` ~ ${version.facts.initial_entry_price_high}`
                        : ""}
                    </dd>
                  </div>
                  <div>
                    <dt>结构失效</dt>
                    <dd>
                      {version.facts.structure_invalidation_price ?? "—"}（
                      {version.facts.structure_invalidation_condition ?? "未填写条件"}）
                    </dd>
                  </div>
                  <div>
                    <dt>仓位 40/30/30</dt>
                    <dd>
                      {version.facts.initial_entry_pct ?? "—"} /{" "}
                      {version.facts.confirmation_add_pct ?? "—"} / {version.facts.t_reserve_pct ?? "—"}
                    </dd>
                  </div>
                  <div>
                    <dt>第一目标</dt>
                    <dd>
                      {version.facts.first_target_price ?? "—"}（减仓{" "}
                      {version.facts.first_target_reduce_pct ?? "—"}%）
                    </dd>
                  </div>
                </dl>

                {version.audit_results && version.audit_results.length > 0 && (
                  <div className="audit-list">
                    {version.audit_results.map((audit) => (
                      <div key={audit.id} className={`audit-item ${levelTone[audit.level?.value ?? ""] ?? ""}`}>
                        <div className="audit-heading">
                          <span className="badge">{audit.level?.label ?? "未知等级"}</span>
                          <span className="muted">{audit.created_at}</span>
                        </div>
                        <p>{audit.summary}</p>
                        <ul className="plain-list">
                          {audit.details?.findings.map((finding) => (
                            <li key={`${audit.id}-${finding.rule}-${finding.message}`}>
                              [{finding.level_zh}] {finding.message}
                            </li>
                          ))}
                        </ul>
                        {audit.details?.skipped_rules && audit.details.skipped_rules.length > 0 && (
                          <ul className="plain-list muted">
                            {audit.details.skipped_rules.map((item) => (
                              <li key={`${audit.id}-skip-${item.rule}`}>未检查：{item.reason}</li>
                            ))}
                          </ul>
                        )}
                        {audit.overrides.length > 0 && (
                          <p className="muted">
                            覆盖记录：{audit.overrides[0].reason}（{audit.overrides[0].operator}）
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>

          <div className="action-bar">
            <label>
              账户权益（审计用，可选）
              <input
                value={auditEquity}
                onChange={(event) => setAuditEquity(event.target.value)}
                placeholder="留空则使用最新快照权益"
              />
            </label>
            {draftVersion && (
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    await api.submitVersion(draftVersion.id);
                    await openDetail(selected.id);
                    return "已提交审计";
                  })
                }
              >
                提交审计
              </button>
            )}
            <button
              type="button"
              disabled={busy || !actionable}
              onClick={() =>
                void run(async () => {
                  if (!actionable) return;
                  await api.runAudit(actionable.id, auditEquity.trim() === "" ? null : auditEquity);
                  await openDetail(selected.id);
                  return "审计完成";
                })
              }
            >
              运行审计
            </button>
            <button
              type="button"
              disabled={busy || !pendingVersion || !latestAudit}
              onClick={() =>
                void run(async () => {
                  if (!pendingVersion) return;
                  await api.decideVersion(pendingVersion.id, { approve: true });
                  await openDetail(selected.id);
                  return "计划版本已生效";
                })
              }
            >
              审计通过并生效
            </button>
            <button
              type="button"
              disabled={busy || !pendingVersion || !latestAudit}
              onClick={() =>
                void run(async () => {
                  if (!pendingVersion) return;
                  await api.decideVersion(pendingVersion.id, { approve: false });
                  await openDetail(selected.id);
                  return "计划版本已拒绝";
                })
              }
            >
              拒绝版本
            </button>
            {pendingVersion && latestAudit?.level?.value === "overridable_fail" && (
              <span className="override-box">
                <input
                  value={overrideReason}
                  onChange={(event) => setOverrideReason(event.target.value)}
                  placeholder="覆盖理由（必填）"
                />
                <button
                  type="button"
                  disabled={busy || overrideReason.trim() === ""}
                  onClick={() =>
                    void run(async () => {
                      await api.decideVersion(pendingVersion.id, {
                        approve: true,
                        user_confirmed: true,
                        override_reason: overrideReason.trim(),
                      });
                      setOverrideReason("");
                      await openDetail(selected.id);
                      return "已覆盖生效，理由已永久记录";
                    })
                  }
                >
                  确认覆盖并生效
                </button>
              </span>
            )}
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  await api.closePlan(selected.id);
                  await openDetail(selected.id);
                  return "计划已关闭";
                })
              }
            >
              关闭计划
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
