"""Prioritized account facts with explicit conflicts and audit events."""

from dataclasses import dataclass, field

from app.account.models import AuditEvent, Conflict, Fact, Fill


@dataclass(slots=True)
class AccountLedger:
    facts: dict[str, Fact] = field(default_factory=dict)
    fills: dict[str, Fill] = field(default_factory=dict)
    batches: dict[str, str] = field(default_factory=dict)
    audit: list[AuditEvent] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)

    def record_fact(self, fact: Fact) -> bool:
        if not fact.key.strip() or not fact.source_id.strip():
            raise ValueError("事实字段和来源不能为空")
        if fact.observed_at.tzinfo is None or fact.observed_at.utcoffset() is None:
            raise ValueError("时间必须包含时区")
        if not fact.value.is_finite() or fact.value < 0:
            raise ValueError("事实值必须是有限非负数")
        old = self.facts.get(fact.key)
        if old is None:
            self.facts[fact.key] = fact
            self.audit.append(AuditEvent("insert", fact.key, fact.source_id, "首次记录"))
            return True
        if old == fact:
            return False
        if old.source.priority > fact.source.priority:
            reason = "低优先级来源不能覆盖高优先级事实"
        elif old.source.priority == fact.source.priority and fact.observed_at < old.observed_at:
            reason = "旧时间戳不能覆盖新事实"
        elif old.source.priority == fact.source.priority and fact.observed_at == old.observed_at:
            reason = "同时间戳事实冲突"
        else:
            reason = ""
        if reason:
            self.conflicts.append(Conflict(fact.key, str(old.value), str(fact.value), reason))
            self.audit.append(AuditEvent("conflict", fact.key, fact.source_id, reason))
            return False
        self.facts[fact.key] = fact
        self.audit.append(
            AuditEvent("supersede", fact.key, fact.source_id,
                       f"替换 {old.source.value}/{old.source_id} 的 {old.value}")
        )
        return True
