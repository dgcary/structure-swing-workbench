import { useState } from "react";
import type { ScreeningResultDto } from "../api";
import { api, screeningStatusName } from "../api";

const EVIDENCE = {
  source: "人工核对",
  reference: "工作台手工录入",
  observed_at: new Date().toISOString(),
};

const hardRiskCodes = [
  "ST",
  "DELISTING",
  "REGULATORY_INVESTIGATION",
  "FINANCIAL_FRAUD",
  "QUALIFIED_AUDIT",
  "SEVERE_DEBT",
  "GOING_CONCERN",
] as const;

const riskNames: Record<string, string> = {
  ST: "ST/风险警示",
  DELISTING: "退市风险",
  REGULATORY_INVESTIGATION: "监管调查",
  FINANCIAL_FRAUD: "财务造假",
  QUALIFIED_AUDIT: "保留意见审计",
  SEVERE_DEBT: "严重债务",
  GOING_CONCERN: "持续经营",
};

const statusTone: Record<string, string> = {
  CANDIDATE: "risk-pass",
  REVIEW: "risk-warning",
  EXCLUDED: "risk-fail",
};

type ProfileKey = "board" | "liquidity" | "size" | "listing_age";

const profileOptions: Record<ProfileKey, { value: string; label: string }[]> = {
  board: [
    { value: "MAIN", label: "主板" },
    { value: "OTHER", label: "非主板" },
    { value: "UNKNOWN", label: "未知" },
  ],
  liquidity: [
    { value: "GOOD", label: "流动性良好" },
    { value: "LOW", label: "低流动性" },
    { value: "UNKNOWN", label: "未知" },
  ],
  size: [
    { value: "MID_LARGE", label: "大中盘" },
    { value: "SMALL", label: "小盘" },
    { value: "UNKNOWN", label: "未知" },
  ],
  listing_age: [
    { value: "ESTABLISHED", label: "非次新" },
    { value: "NEW", label: "次新" },
    { value: "UNKNOWN", label: "未知" },
  ],
};

export function CandidatesSection({ backendReady }: { backendReady: boolean }) {
  const [symbol, setSymbol] = useState("");
  const [name, setName] = useState("");
  const [profile, setProfile] = useState<Record<ProfileKey, string>>({
    board: "MAIN",
    liquidity: "GOOD",
    size: "MID_LARGE",
    listing_age: "ESTABLISHED",
  });
  const [riskStates, setRiskStates] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ScreeningResultDto | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      const payload = {
        symbol: symbol.trim(),
        name: name.trim(),
        board: { value: profile.board, evidence: EVIDENCE },
        liquidity: { value: profile.liquidity, evidence: EVIDENCE },
        size: { value: profile.size, evidence: EVIDENCE },
        listing_age: { value: profile.listing_age, evidence: EVIDENCE },
        risks: hardRiskCodes.map((code) => ({
          code,
          state: riskStates[code] ?? "UNKNOWN",
          evidence: EVIDENCE,
        })),
      };
      setResult(await api.screenCandidate(payload));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="section">
      <div className="panel">
        <div className="panel-heading">
          <h2>候选筛选</h2>
          <span className="muted">客观分类与风险状态均需人工核对录入；不自动判断 Setup。</span>
        </div>
        <form
          className="plan-form"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <div className="form-row">
            <label>
              证券代码
              <input
                required
                value={symbol}
                onChange={(event) => setSymbol(event.target.value)}
                placeholder="600000"
              />
            </label>
            <label>
              证券名称
              <input
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="浦发银行"
              />
            </label>
            {(Object.keys(profileOptions) as ProfileKey[]).map((key) => (
              <label key={key}>
                {key === "board" ? "板块" : key === "liquidity" ? "流动性" : key === "size" ? "市值" : "上市时间"}
                <select
                  value={profile[key]}
                  onChange={(event) => setProfile({ ...profile, [key]: event.target.value })}
                >
                  {profileOptions[key].map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <fieldset className="risk-grid">
            <legend>重大风险核对（硬性红线）</legend>
            {hardRiskCodes.map((code) => (
              <label key={code}>
                {riskNames[code]}
                <select
                  value={riskStates[code] ?? "UNKNOWN"}
                  onChange={(event) => setRiskStates({ ...riskStates, [code]: event.target.value })}
                >
                  <option value="ABSENT">未见</option>
                  <option value="PRESENT">存在</option>
                  <option value="UNKNOWN">未知</option>
                </select>
              </label>
            ))}
          </fieldset>
          <button type="submit" disabled={busy || !backendReady}>
            运行筛选
          </button>
        </form>
      </div>

      {error && (
        <p role="alert" className="alert">
          筛选失败：{error}
        </p>
      )}

      {result && (
        <div className="panel">
          <div className="panel-heading">
            <h2>
              {result.name}（{result.symbol}）
            </h2>
            <span className={`badge ${statusTone[result.status] ?? ""}`}>
              {screeningStatusName(result.status)}
            </span>
          </div>
          {result.missing_risk_checks.length > 0 && (
            <p className="muted">
              待核实：{result.missing_risk_checks.map((code) => riskNames[code] ?? code).join("、")}
            </p>
          )}
          <ul className="plain-list">
            {result.messages.map((message) => (
              <li key={message}>{message}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
