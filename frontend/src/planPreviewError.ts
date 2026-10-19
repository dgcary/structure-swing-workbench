/** Convert FastAPI/Pydantic validation failures into safe Chinese field hints. */
const fieldNames: Record<string, string> = {
  symbol: "证券代码",
  account_equity: "账户权益",
  planned_quantity: "计划数量",
  planned_entry_price: "入场价格",
  invalidation_price: "结构失效价",
  initial_pct: "位置试仓比例",
  confirmation_pct: "确认加仓比例",
  t_reserve_pct: "机动仓比例",
  action_type: "用户计划动作",
  structure_invalidated: "结构是否失效",
};

type ValidationItem = {
  loc?: unknown;
  type?: unknown;
  msg?: unknown;
};

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function describe(item: ValidationItem): string {
  const loc = Array.isArray(item.loc) ? item.loc : [];
  const key = loc.find((part): part is string =>
    typeof part === "string" && Object.hasOwn(fieldNames, part));
  const label = key ? fieldNames[key] : "计划字段";
  if (item.type === "value_error" && typeof item.msg === "string") {
    const message = item.msg.replace(/^Value error,\s*/i, "").trim();
    if (message && /[\u3400-\u9fff]/u.test(message)) {
      return `${label}：${message.slice(0, 160)}`;
    }
  }
  const reason: Record<string, string> = {
    missing: "不能为空",
    string_pattern_mismatch: "格式不正确",
    greater_than: "必须大于零或指定下限",
    greater_than_equal: "不能小于允许下限",
    less_than: "必须小于允许上限",
    less_than_equal: "不能超过允许上限",
    decimal_parsing: "必须填写有效数字",
    decimal_type: "必须填写有效数字",
    finite_number: "必须填写有限数字",
    enum: "不是允许的操作类型",
    literal_error: "不在允许范围内",
    bool_parsing: "必须明确选择是或否",
  };
  return `${label}：${reason[String(item.type)] ?? "输入不符合要求"}`;
}

/** Never expose raw server payloads or suggest that a failed preview passed. */
export function planPreviewError(status: number, payload: unknown): string {
  if (status !== 422 || !isObject(payload)) {
    return "预审接口失败，请稍后重试；本次未生成审计结果。";
  }
  const detail = payload.detail;
  if (typeof detail === "string") {
    return /[\u3400-\u9fff]/u.test(detail)
      ? detail.slice(0, 200)
      : "计划输入校验失败，请核对已填写字段。";
  }
  if (!Array.isArray(detail) || detail.length === 0) {
    return "计划输入校验失败，请核对已填写字段。";
  }
  const messages = detail.slice(0, 4).map((item: unknown) =>
    describe(isObject(item) ? item : {}));
  return `计划输入校验失败：${messages.join("；")}`;
}
