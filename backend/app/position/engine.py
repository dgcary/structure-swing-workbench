from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True)
class PositionState:
    core_quantity: Decimal
    core_cost: Decimal
    broker_quantity: Decimal
    broker_cost: Decimal
    realized_t_pnl: Decimal = Decimal(0)

    @property
    def effective_cost(self) -> Decimal:
        if self.core_quantity == 0:
            return Decimal(0)
        return self.core_cost - self.realized_t_pnl / self.core_quantity

    def reverse_t_exposure(self, quantity: Decimal, price: Decimal) -> Decimal:
        return quantity * price

    def t_stop_risk(self, quantity: Decimal, entry: Decimal, stop: Decimal) -> Decimal:
        return quantity * abs(entry - stop)
