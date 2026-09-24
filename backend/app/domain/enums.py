from enum import Enum


class LabeledEnum(str, Enum):
    @property
    def label_zh(self) -> str:
        return ENUM_LABELS[type(self)][self]

    @classmethod
    def labels_zh(cls) -> dict[str, str]:
        return {member.value: ENUM_LABELS[cls][member] for member in cls}


class SetupType(LabeledEnum):
    C = "c"
    A = "a"
    B = "b"


class StructureStage(LabeledEnum):
    EARLY = "early"
    MIDDLE = "middle"
    LATE = "late"


class PlanStatus(LabeledEnum):
    ACTIVE = "active"
    EXITING = "exiting"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class PlanVersionState(LabeledEnum):
    PENDING_AUDIT = "pending_audit"
    EFFECTIVE = "effective"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class ActionType(LabeledEnum):
    INITIAL_ENTRY = "initial_entry"
    CONFIRMATION_ADD = "confirmation_add"
    ORDINARY_ADD = "ordinary_add"
    POSITIVE_T_SELL = "positive_t_sell"
    POSITIVE_T_BUYBACK = "positive_t_buyback"
    REVERSE_T_BUY = "reverse_t_buy"
    REVERSE_T_SELL = "reverse_t_sell"
    TAKE_PROFIT = "take_profit"
    REDUCE = "reduce"
    EXIT = "exit"


class ActionStatus(LabeledEnum):
    PLANNED = "planned"
    AUDITED = "audited"
    EXECUTING = "executing"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class OrderSide(LabeledEnum):
    BUY = "buy"
    SELL = "sell"


class PositionBucketType(LabeledEnum):
    CORE = "core"
    T = "t"


class AuditLevel(LabeledEnum):
    PASS = "pass"
    WARNING = "warning"
    OVERRIDABLE_FAIL = "overridable_fail"
    HARD_FAIL = "hard_fail"


class TargetType(LabeledEnum):
    PRIOR_HIGH = "prior_high"
    RANGE_TOP = "range_top"
    MAJOR_RESISTANCE = "major_resistance"
    OTHER = "other"


ENUM_LABELS: dict[type[LabeledEnum], dict[LabeledEnum, str]] = {
    SetupType: {
        SetupType.C: "C｜上升趋势早中段回踩",
        SetupType.A: "A｜横盘区间下沿",
        SetupType.B: "B｜深回撤反转",
    },
    StructureStage: {
        StructureStage.EARLY: "早段",
        StructureStage.MIDDLE: "中段",
        StructureStage.LATE: "后段",
    },
    PlanStatus: {
        PlanStatus.ACTIVE: "有效",
        PlanStatus.EXITING: "退出执行中",
        PlanStatus.CLOSED: "已关闭",
        PlanStatus.CANCELLED: "已取消",
    },
    PlanVersionState: {
        PlanVersionState.PENDING_AUDIT: "待审计",
        PlanVersionState.EFFECTIVE: "当前有效版本",
        PlanVersionState.SUPERSEDED: "历史版本",
        PlanVersionState.REJECTED: "未通过版本",
    },
    ActionType: {
        ActionType.INITIAL_ENTRY: "初始建仓",
        ActionType.CONFIRMATION_ADD: "确认加仓",
        ActionType.ORDINARY_ADD: "普通加仓",
        ActionType.POSITIVE_T_SELL: "正T先卖",
        ActionType.POSITIVE_T_BUYBACK: "正T买回",
        ActionType.REVERSE_T_BUY: "反T先买",
        ActionType.REVERSE_T_SELL: "反T卖出",
        ActionType.TAKE_PROFIT: "止盈",
        ActionType.REDUCE: "减仓",
        ActionType.EXIT: "退出",
    },
    ActionStatus: {
        ActionStatus.PLANNED: "计划中",
        ActionStatus.AUDITED: "已审计",
        ActionStatus.EXECUTING: "执行中",
        ActionStatus.PARTIALLY_FILLED: "部分成交",
        ActionStatus.FILLED: "已完成",
        ActionStatus.CANCELLED: "已取消",
        ActionStatus.REJECTED: "不可执行",
    },
    OrderSide: {
        OrderSide.BUY: "买入",
        OrderSide.SELL: "卖出",
    },
    PositionBucketType: {
        PositionBucketType.CORE: "核心仓",
        PositionBucketType.T: "T仓",
    },
    AuditLevel: {
        AuditLevel.PASS: "通过",
        AuditLevel.WARNING: "警告",
        AuditLevel.OVERRIDABLE_FAIL: "可覆盖失败",
        AuditLevel.HARD_FAIL: "硬性失败",
    },
    TargetType: {
        TargetType.PRIOR_HIGH: "前高",
        TargetType.RANGE_TOP: "箱体上沿",
        TargetType.MAJOR_RESISTANCE: "主要压力",
        TargetType.OTHER: "其他",
    },
}
