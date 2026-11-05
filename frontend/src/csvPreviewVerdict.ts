/** Fail-closed presentation of isolated CSV validation; never imply broker import. */
export type CSVPreviewCounts = {
  row_count: number;
  new_facts_in_isolated_preview: number;
  duplicates_in_isolated_preview: number;
  conflicts_in_isolated_preview: number;
  valid_csv_structure: boolean;
};

export type CSVPreviewVerdict = {
  level: "error" | "warning" | "ok";
  heading: string;
  explanation: string;
};

export function csvPreviewVerdict(data: CSVPreviewCounts): CSVPreviewVerdict {
  const counts = [
    data.row_count, data.new_facts_in_isolated_preview,
    data.duplicates_in_isolated_preview, data.conflicts_in_isolated_preview,
  ];
  if (data.valid_csv_structure !== true || counts.some((value) =>
    !Number.isSafeInteger(value) || value < 0) || data.row_count === 0) {
    throw new Error("隔离校验结果缺失或统计无效；不可认定导入成功。");
  }
  if (data.conflicts_in_isolated_preview > 0) {
    return {
      level: "error",
      heading: "检测到账本内部冲突 · 校验未通过",
      explanation: "请核对相互冲突的账户或成交事实；未保存、未导入，不能据此更新持仓。",
    };
  }
  if (data.duplicates_in_isolated_preview > 0) {
    return {
      level: "warning",
      heading: "发现重复记录 · 请人工核对",
      explanation: "重复事实没有作为新增事实处理；此处仅为隔离预览，未保存或导入。",
    };
  }
  return {
    level: "ok",
    heading: "隔离校验完成 · 未保存或导入",
    explanation: "仅检查本次输入，尚未核对真实账户或券商持仓。",
  };
}
