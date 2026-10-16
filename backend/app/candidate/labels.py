"""Chinese presentation labels for M7; canonical codes and evidence remain unchanged."""

RISK_LABELS = {
    "ST": "ST 风险",
    "DELISTING": "退市风险",
    "REGULATORY_INVESTIGATION": "监管立案",
    "FINANCIAL_FRAUD": "财务造假",
    "QUALIFIED_AUDIT": "非标准审计意见",
    "SEVERE_DEBT": "严重债务风险",
    "GOING_CONCERN": "持续经营风险",
    "EARNINGS_DECLINE": "业绩下滑",
    "SHAREHOLDER_REDUCTION": "大股东减持",
    "SHARE_PLEDGE": "股权质押",
    "MAJOR_LITIGATION": "重大诉讼",
    "CASH_FLOW_DETERIORATION": "现金流恶化",
    "VALUATION_HIGH": "估值偏高",
}

STATUS_LABELS = {
    "CANDIDATE": "候选待人工判断",
    "REVIEW": "资料待核实",
    "EXCLUDED": "风险排除",
}

RISK_STATE_LABELS = {
    "PRESENT": "已确认存在",
    "ABSENT": "已核实未发现",
    "UNKNOWN": "状态未知",
}

PROFILE_LABELS = {
    "board": {
        "MAIN": "主板",
        "OTHER": "非主板",
        "UNKNOWN": "板块未知",
    },
    "liquidity": {
        "GOOD": "流动性良好",
        "LOW": "流动性偏低",
        "UNKNOWN": "流动性未知",
    },
    "size": {
        "MID_LARGE": "大中盘",
        "SMALL": "小盘",
        "UNKNOWN": "市值分类未知",
    },
    "listing_age": {
        "ESTABLISHED": "非次新",
        "NEW": "次新",
        "UNKNOWN": "上市时间分类未知",
    },
}

REVIEW_LANE_LABELS = {
    "C": "C 类候选复核",
    "A": "A 类候选复核",
    "B": "B 类候选复核",
    None: "未指定候选复核通道",
}
