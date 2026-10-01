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
        cycle = TCycle(direction=direction, open_quantity=quantity, open_price=price)
        self.t_cycles.append(cycle)
        return cycle

    def close_t_cycle(self, cycle: TCycle, quantity: Decimal, price: Decimal) -> Decimal:
        was_open = cycle.status is TCycleStatus.OPEN
        pnl = cycle.match(quantity, price)
        self.realized_t_pnl += pnl
        if was_open and cycle.status is TCycleStatus.CLOSED:
            self.completed_t_cycles_today += 1
        return pnl

    def convert_open_cycles_at_day_end(self) -> tuple[TCycle, ...]:
        converted: list[TCycle] = []
        for cycle in self.t_cycles:
            if cycle.status is TCycleStatus.OPEN:
                cycle.status = TCycleStatus.CONVERTED
                converted.append(cycle)
        return tuple(converted)
