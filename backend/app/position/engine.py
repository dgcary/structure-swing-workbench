from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum


class TDirection(str, Enum):
    POSITIVE = "positive"
    REVERSE = "reverse"


class TCycleStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    CONVERTED = "converted"


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
        return quantity * price

    def t_stop_risk(self, quantity: Decimal, entry: Decimal, stop: Decimal) -> Decimal:
        return quantity * abs(entry - stop)

    def start_t_cycle(self, direction: TDirection, quantity: Decimal, price: Decimal) -> TCycle:
        if quantity <= 0:
            raise ValueError("T循环数量必须大于0")
        if self.completed_t_cycles_today >= 2:
            raise ValueError("同一股票单日最多2个完整T闭环")
        if direction is TDirection.POSITIVE:
            reserved = sum(
                item.remaining_quantity
                for item in self.t_cycles
                if item.direction is TDirection.POSITIVE and item.status is TCycleStatus.OPEN
            )
            if quantity + reserved > self.broker_quantity - self.core_quantity:
                raise ValueError("T仓不得侵蚀核心仓")
        cycle = TCycle(direction=direction, open_quantity=quantity, open_price=price)
        self.t_cycles.append(cycle)
        if direction is TDirection.REVERSE:
            self.apply_broker_buy(quantity, price)
        else:
            self.apply_broker_sell(quantity)
        return cycle

    def close_t_cycle(self, cycle: TCycle, quantity: Decimal, price: Decimal) -> Decimal:
        was_open = cycle.status is TCycleStatus.OPEN
        pnl = cycle.match(quantity, price)
        if cycle.direction is TDirection.REVERSE:
            self.apply_broker_sell(quantity)
        else:
            self.apply_broker_buy(quantity, price)
        self.realized_t_pnl += pnl
        if was_open and cycle.status is TCycleStatus.CLOSED:
            self.completed_t_cycles_today += 1
        return pnl

    def apply_broker_buy(self, quantity: Decimal, price: Decimal) -> None:
        if quantity <= 0:
            raise ValueError("成交数量必须大于0")
        total_cost = self.broker_quantity * self.broker_cost + quantity * price
        self.broker_quantity += quantity
        self.broker_cost = total_cost / self.broker_quantity

    def apply_broker_sell(self, quantity: Decimal) -> None:
        if quantity <= 0 or quantity > self.broker_quantity:
            raise ValueError("卖出数量必须大于0且不超过券商持仓")
        self.broker_quantity -= quantity
        if self.broker_quantity == 0:
            self.broker_cost = Decimal(0)

    def convert_open_cycles_at_day_end(self) -> tuple[TCycle, ...]:
        converted: list[TCycle] = []
        for cycle in self.t_cycles:
            if cycle.status is not TCycleStatus.OPEN:
                continue
            remaining = cycle.remaining_quantity
            if remaining > 0:
                if cycle.direction is TDirection.REVERSE:
                    self._apply_core_buy(remaining, cycle.open_price)
                else:
                    self._apply_core_sell(remaining)
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
        if quantity <= 0 or quantity > self.core_quantity:
            raise ValueError("目标减仓数量必须大于0且不超过核心仓")
        self.core_quantity -= quantity
        self.apply_broker_sell(quantity)
        if self.core_quantity == 0:
            self.core_cost = Decimal(0)
