from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum


class TDirection(str, Enum):
    POSITIVE = "positive"
    REVERSE = "reverse"


class TCycleStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    CONVERTED = "converted"


class CoreBuyAction(str, Enum):
    BUY_INITIAL = "BUY_INITIAL"
    ADD = "ADD"


@dataclass(frozen=True, slots=True)
class CoreBuyFill:
    action: CoreBuyAction
    quantity: Decimal
    price: Decimal


class BrokerInventoryConflict(ValueError):
    """Broker ledger conflicts with protected core/reverse-T inventory."""


@dataclass(slots=True)
class TCycle:
    direction: TDirection
    open_quantity: Decimal
    open_price: Decimal
    matched_quantity: Decimal = Decimal(0)
    matched_value: Decimal = Decimal(0)
    status: TCycleStatus = TCycleStatus.OPEN

    @property
    def remaining_quantity(self) -> Decimal:
        return self.open_quantity - self.matched_quantity

    @property
    def matched_gross_pnl(self) -> Decimal:
        basis = self.matched_quantity * self.open_price
        return (basis - self.matched_value if self.direction is TDirection.POSITIVE
                else self.matched_value - basis)

    def match(self, quantity: Decimal, price: Decimal) -> Decimal:
        if self.status is not TCycleStatus.OPEN:
            raise ValueError("T循环已结束")
        if quantity <= 0 or quantity > self.remaining_quantity:
            raise ValueError("闭环数量必须大于0且不超过未匹配数量")
        self.matched_quantity += quantity
        self.matched_value += quantity * price
        if self.remaining_quantity == 0:
            self.status = TCycleStatus.CLOSED
        if self.direction is TDirection.POSITIVE:
            return quantity * (self.open_price - price)
        return quantity * (price - self.open_price)


@dataclass(slots=True)
class PositionState:
    core_quantity: Decimal
    core_cost: Decimal
    broker_quantity: Decimal
    broker_cost: Decimal
    realized_t_pnl: Decimal = Decimal(0)
    t_cycles: list[TCycle] = field(default_factory=list)
    completed_t_cycles_today: int = 0
    ordinary_t_addition_quantity: Decimal = Decimal(0)
    ordinary_t_reduction_quantity: Decimal = Decimal(0)
    trading_day: date | None = None
    # A-share T+1: today's purchases are not yesterday's sellable inventory.
    same_day_buy_quantity: Decimal = Decimal(0)
    estimated_broker_cost: Decimal | None = None
    core_same_day_buy_quantity: Decimal = Decimal(0)
    core_buy_fills: list[CoreBuyFill] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.estimated_broker_cost is None:
            self.estimated_broker_cost = self.broker_cost

    @property
    def broker_display_cost(self) -> Decimal:
        return self.broker_cost

    def set_broker_display_cost(self, cost: Decimal) -> None:
        if not cost.is_finite():
            raise ValueError("券商显示成本必须为有限数字")
        self.broker_cost = cost

    def reconcile_broker_cost(self, quantity: Decimal, cost: Decimal) -> None:
        if not quantity.is_finite() or not cost.is_finite():
            raise ValueError("券商对账数据必须为有限数字")
        if quantity != self.broker_quantity:
            raise BrokerInventoryConflict("券商持仓数量不一致，不能覆盖显示成本")
        self.broker_cost = cost

    @property
    def sellable_core_quantity(self) -> Decimal:
        return self.core_quantity - self.core_same_day_buy_quantity

    @property
    def pending_t_pnl(self) -> Decimal:
        return sum((c.matched_gross_pnl for c in self.t_cycles
                    if c.status is TCycleStatus.OPEN), Decimal(0))

    @property
    def converted_t_pnl(self) -> Decimal:
        return sum((c.matched_gross_pnl for c in self.t_cycles
                    if c.status is TCycleStatus.CONVERTED), Decimal(0))

    @property
    def old_sellable_quantity(self) -> Decimal:
        return self.broker_quantity - self.same_day_buy_quantity

    @property
    def effective_cost(self) -> Decimal:
        if self.core_quantity == 0:
            return Decimal(0)
        return self.core_cost - self.realized_t_pnl / self.core_quantity

    @property
    def reverse_t_temporary_exposure(self) -> Decimal:
        return sum(
            cycle.remaining_quantity * cycle.open_price
            for cycle in self.t_cycles
            if cycle.direction is TDirection.REVERSE and cycle.status is TCycleStatus.OPEN
        )

    def reverse_t_exposure(self, quantity: Decimal, price: Decimal) -> Decimal:
        if quantity < 0 or price < 0:
            raise ValueError("风险暴露数量和价格不得为负")
        return quantity * price

    def total_market_exposure(self, market_price: Decimal) -> Decimal:
        """Return live gross exposure, including temporary reverse-T inventory."""
        if market_price < 0:
            raise ValueError("市场价格不得为负")
        return self.broker_quantity * market_price

    def t_stop_risk(self, quantity: Decimal, entry: Decimal, stop: Decimal) -> Decimal:
        """Long reverse-T downside risk; stop must be below the purchase price."""
        if quantity < 0 or entry < 0 or stop < 0:
            raise ValueError("止损风险数量和价格不得为负")
        if stop >= entry:
            raise ValueError("反T止损价必须低于买入价")
        return quantity * (entry - stop)

    def start_t_cycle(self, direction: TDirection, quantity: Decimal, price: Decimal) -> TCycle:
        if not isinstance(direction, TDirection):
            raise TypeError("T循环方向必须为正T或反T")
        if quantity <= 0:
            raise ValueError("T循环数量必须大于0")
        if price <= 0:
            raise ValueError("T循环成交价格必须大于0")
        if self.completed_t_cycles_today >= 2:
            raise ValueError("同一股票单日最多2个完整T闭环")
        if direction is TDirection.POSITIVE:
            if quantity > self._available_inventory_for_positive_t():
                raise ValueError("T仓不得侵蚀核心仓")
        elif quantity > self._available_old_inventory_for_reverse_t():
            raise ValueError("反T必须有足够昨日可卖持仓，且不得侵蚀核心仓")
        cycle = TCycle(direction=direction, open_quantity=quantity, open_price=price)
        self.t_cycles.append(cycle)
        if direction is TDirection.REVERSE:
            self.apply_broker_buy(quantity, price)
        else:
            self.apply_broker_sell(quantity)
        return cycle

    def add_t_open_fill(self, cycle: TCycle, quantity: Decimal, price: Decimal) -> None:
        """Aggregate split opening fills into one logical T cycle."""
        if not any(owned is cycle for owned in self.t_cycles):
            raise ValueError("只能追加当前持仓状态所属的T循环")
        if cycle.status is not TCycleStatus.OPEN or cycle.matched_quantity != 0:
            raise ValueError("仅允许在闭环成交前追加未结束T循环的开仓成交")
        if self.completed_t_cycles_today >= 2:
            raise ValueError("同一股票单日最多2个完整T闭环")
        if quantity <= 0 or price <= 0:
            raise ValueError("追加开仓成交数量和价格必须大于0")
        if cycle.direction is TDirection.POSITIVE:
            if quantity > self._available_inventory_for_positive_t():
                raise ValueError("T仓不得侵蚀核心仓")
            self.apply_broker_sell(quantity)
        else:
            if quantity > self._available_old_inventory_for_reverse_t():
                raise ValueError("反T必须有足够昨日可卖持仓，且不得侵蚀核心仓")
            self.apply_broker_buy(quantity, price)
        total_value = cycle.open_quantity * cycle.open_price + quantity * price
        cycle.open_quantity += quantity
        cycle.open_price = total_value / cycle.open_quantity

    def close_t_cycle(self, cycle: TCycle, quantity: Decimal, price: Decimal) -> Decimal:
        if not any(owned is cycle for owned in self.t_cycles):
            raise ValueError("只能闭环当前持仓状态所属的T循环")
        if price <= 0:
            raise ValueError("T循环成交价格必须大于0")
        was_open = cycle.status is TCycleStatus.OPEN
        if was_open and self.completed_t_cycles_today >= 2:
            raise ValueError("同一股票单日最多2个完整T闭环")
        # Preflight before changing cycle fills/P&L. The closing leg
        # releases only its own reverse-T reservation.
        if was_open and cycle.direction is TDirection.REVERSE:
            if quantity <= 0 or quantity > cycle.remaining_quantity:
                raise ValueError("闭环数量必须大于0且不超过未匹配数量")
            self._check_broker_sell(quantity, reverse_release=quantity)
        pnl = cycle.match(quantity, price)
        if cycle.direction is TDirection.REVERSE:
            self._record_broker_sell(quantity)
        else:
            self.apply_broker_buy(quantity, price)
        if was_open and cycle.status is TCycleStatus.CLOSED:
            self.realized_t_pnl += cycle.matched_gross_pnl
            self.completed_t_cycles_today += 1
        return pnl

    def _open_reverse_quantity(self) -> Decimal:
        return sum(
            cycle.remaining_quantity
            for cycle in self.t_cycles
            if cycle.direction is TDirection.REVERSE and cycle.status is TCycleStatus.OPEN
        )

    def _available_inventory_for_positive_t(self) -> Decimal:
        return (
            self.old_sellable_quantity
            - self.sellable_core_quantity
            - self._open_reverse_quantity()
        )

    def _available_old_inventory_for_reverse_t(self) -> Decimal:
        return (
            self.old_sellable_quantity
            - self.sellable_core_quantity
            - self._open_reverse_quantity()
        )

    def apply_core_buy(
        self, quantity: Decimal, price: Decimal, action: CoreBuyAction
    ) -> None:
        """Record an authorized initial/add fill atomically, including T+1."""
        if not isinstance(action, CoreBuyAction):
            raise TypeError("核心仓买入动作必须为 BUY_INITIAL 或 ADD")
        if quantity <= 0 or price <= 0:
            raise ValueError("核心仓成交数量和价格必须大于0")
        self.apply_broker_buy(quantity, price)
        self._apply_core_buy(quantity, price)
        self.core_same_day_buy_quantity += quantity
        self.core_buy_fills.append(CoreBuyFill(action, quantity, price))

    def apply_broker_buy(self, quantity: Decimal, price: Decimal) -> None:
        if quantity <= 0 or price <= 0:
            raise ValueError("成交数量和价格必须大于0")
        total_cost = self.broker_quantity * self.estimated_broker_cost + quantity * price
        self.broker_quantity += quantity
        self.same_day_buy_quantity += quantity
        self.estimated_broker_cost = total_cost / self.broker_quantity

    def _check_broker_sell(
        self,
        quantity: Decimal,
        *,
        core_after: Decimal | None = None,
        reverse_release: Decimal = Decimal(0),
    ) -> None:
        if quantity <= 0 or quantity > self.old_sellable_quantity:
            raise ValueError("卖出数量必须大于0且不超过昨日可卖持仓")
        protected_core = self.sellable_core_quantity if core_after is None else core_after
        remaining_reserved = self._open_reverse_quantity() - reverse_release
        if remaining_reserved < 0:
            raise ValueError("反T释放数量超过已预留旧仓")
        if self.old_sellable_quantity - quantity < protected_core + remaining_reserved:
            raise BrokerInventoryConflict(
                "外部对账冲突：卖出将侵蚀核心仓或反T预留旧仓，"
                "请核对券商成交后再调整持仓"
            )

    def _record_broker_sell(self, quantity: Decimal) -> None:
        """Commit a sell only after the relevant inventory preflight passes."""
        self.broker_quantity -= quantity
        if self.broker_quantity == 0:
            self.estimated_broker_cost = Decimal(0)

    def apply_broker_sell(self, quantity: Decimal) -> None:
        """Ordinary sell; never consume protected core or reverse-T stock."""
        self._check_broker_sell(quantity)
        self._record_broker_sell(quantity)

    def advance_trading_day(self, next_day: date) -> tuple[TCycle, ...]:
        """Roll unfinished T legs into ordinary positions and reset the daily quota."""
        if not isinstance(next_day, date):
            raise TypeError("交易日必须为 date 类型")
        if self.trading_day is None:
            if self.t_cycles or self.completed_t_cycles_today:
                raise ValueError("已有T成交记录，不能补录未知的初始交易日")
            self.trading_day = next_day
            return ()
        if next_day < self.trading_day:
            raise ValueError("交易日不得倒退")
        if next_day == self.trading_day:
            return ()
        converted = self.convert_open_cycles_at_day_end()
        self.completed_t_cycles_today = 0
        self.same_day_buy_quantity = Decimal(0)
        self.core_same_day_buy_quantity = Decimal(0)
        self.trading_day = next_day
        return converted

    def convert_open_cycles_at_day_end(self) -> tuple[TCycle, ...]:
        # Validate all pending additions before mutating any cycle.
        reverse_additions = sum(
            (
                cycle.remaining_quantity
                for cycle in self.t_cycles
                if cycle.status is TCycleStatus.OPEN
                and cycle.direction is TDirection.REVERSE
            ),
            Decimal(0),
        )
        if self.core_quantity + reverse_additions > self.broker_quantity:
            raise ValueError("日终未闭环T转普通仓将超过券商持仓，请先核对外部成交")
        converted: list[TCycle] = []
        for cycle in self.t_cycles:
            if cycle.status is not TCycleStatus.OPEN:
                continue
            remaining = cycle.remaining_quantity
            if remaining > 0:
                if cycle.direction is TDirection.REVERSE:
                    self._apply_core_buy(remaining, cycle.open_price)
                    self.core_same_day_buy_quantity += remaining
                    self.ordinary_t_addition_quantity += remaining
                else:
                    self.ordinary_t_reduction_quantity += remaining
            cycle.status = TCycleStatus.CONVERTED
            converted.append(cycle)
        return tuple(converted)

    def _apply_core_buy(self, quantity: Decimal, price: Decimal) -> None:
        total_cost = self.core_quantity * self.core_cost + quantity * price
        self.core_quantity += quantity
        self.core_cost = total_cost / self.core_quantity

    def _apply_core_sell(self, quantity: Decimal) -> None:
        if quantity > self.core_quantity:
            raise ValueError("日终普通减仓不得超过核心仓")
        self.core_quantity -= quantity
        if self.core_quantity == 0:
            self.core_cost = Decimal(0)

    def apply_target_reduction(self, quantity: Decimal) -> None:
        if quantity <= 0 or quantity > self.sellable_core_quantity:
            raise ValueError("目标减仓数量必须大于0且不超过昨日可卖核心仓")
        # Authorized core reduction: preflight the projected core inventory
        # and all outstanding reverse-T reservations before any mutation.
        try:
            self._check_broker_sell(quantity, core_after=self.sellable_core_quantity - quantity)
        except BrokerInventoryConflict as exc:
            raise BrokerInventoryConflict(
                "目标减仓不得占用未闭环反T预留持仓或当日买入股份"
            ) from exc
        self.core_quantity -= quantity
        self._record_broker_sell(quantity)
        if self.core_quantity == 0:
            self.core_cost = Decimal(0)
