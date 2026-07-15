"""Alert system — rule-based health monitoring with pluggable handlers.

Alerts fire when system metrics cross configurable thresholds.
Integrates with Scheduler (auto-evaluate each tick) and Dashboard.

Usage:
    from jarvis.alerts import AlertManager, AlertRule

    mgr = AlertManager()
    mgr.add_rule(AlertRule(
        name="low_success_rate",
        metric="success_rate",
        threshold=0.5,
        operator="lt",
        severity="critical",
        message="Task success rate dropped below 50%",
    ))

    # Integrate into Scheduler:
    sched.on_tick = mgr.evaluate  # auto-check after each event loop tick
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# Types
# ══════════════════════════════════════════════════════════════════


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = auto()
    WARNING = auto()
    CRITICAL = auto()


@dataclass
class AlertRule:
    """A monitoring rule that fires when a metric crosses a threshold.

    Examples:
        AlertRule("low_success", "success_rate", 0.5, "lt", "critical",
                  "Success rate below 50%")
        AlertRule("high_failures", "task_failures_per_minute", 10, "gt",
                  "warning", "More than 10 failures/min")
        AlertRule("scheduler_down", "scheduler_running", 1, "eq",
                  "critical", "Scheduler has stopped")
    """

    name: str
    metric: str                       # key in the state dict
    threshold: float
    operator: str = "lt"              # lt / gt / eq / gte / lte
    severity: str = "warning"         # info / warning / critical
    message: str = ""
    cooldown_seconds: float = 60.0    # min time between repeated fires
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


@dataclass
class Alert:
    """A fired alert instance."""

    rule_name: str
    severity: str
    message: str
    metric: str
    current_value: float
    threshold: float
    operator: str
    timestamp: float  # epoch seconds


AlertHandler = Callable[[Alert], None]


# ══════════════════════════════════════════════════════════════════
# Manager
# ══════════════════════════════════════════════════════════════════


class AlertManager:
    """Manages alert rules, evaluates state, dispatches to handlers."""

    def __init__(self) -> None:
        self._rules: dict[str, AlertRule] = {}
        self._handlers: list[AlertHandler] = []
        self._fired_history: list[Alert] = []  # capped at 200
        self._last_fired: dict[str, float] = {}  # rule_name → timestamp

        # Built-in: log handler
        self._handlers.append(self._log_handler)

    # ── Rule management ────────────────────────────────────────────

    def add_rule(self, rule: AlertRule) -> None:
        """Register an alert rule."""
        self._rules[rule.name] = rule
        logger.debug("[Alerts] Rule added: %s (%s %s %.2f)",
                     rule.name, rule.metric, rule.operator, rule.threshold)

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name."""
        if name in self._rules:
            del self._rules[name]
            self._last_fired.pop(name, None)
            return True
        return False

    def disable_rule(self, name: str) -> bool:
        """Disable a rule. Return True if the rule exists."""
        rule = self._rules.get(name)
        if rule is None:
            return False
        rule.enabled = False
        return True

    def enable_rule(self, name: str) -> bool:
        """Enable a rule. Return True if the rule exists."""
        rule = self._rules.get(name)
        if rule is None:
            return False
        rule.enabled = True
        return True

    def get_rule(self, name: str) -> Optional[AlertRule]:
        """Get a rule by name (returns a copy)."""
        r = self._rules.get(name)
        if r is None:
            return None
        return AlertRule(
            name=r.name, metric=r.metric, threshold=r.threshold,
            operator=r.operator, severity=r.severity, message=r.message,
            cooldown_seconds=r.cooldown_seconds, enabled=r.enabled,
            tags=list(r.tags),
        )

    def list_rules(self) -> list[AlertRule]:
        """List all rules (copies)."""
        return [self.get_rule(name) for name in self._rules]

    # ── Handler management ─────────────────────────────────────────

    def add_handler(self, handler: AlertHandler) -> None:
        """Register a custom alert handler."""
        self._handlers.append(handler)

    # ── Evaluation ─────────────────────────────────────────────────

    def evaluate(self, state: dict) -> list[Alert]:
        """Evaluate all rules against a state snapshot, firing alerts.

        Args:
            state: Dict with metric keys (e.g. 'success_rate', 'task_failures',
                   'active_ministers', 'scheduler_running').

        Returns:
            List of newly fired alerts.
        """
        import time

        now = time.time()
        fired: list[Alert] = []

        for rule in self._rules.values():
            if not rule.enabled:
                continue

            # Cooldown check
            last = self._last_fired.get(rule.name, 0)
            if now - last < rule.cooldown_seconds:
                continue

            # Get metric value
            value = state.get(rule.metric)
            if value is None:
                continue  # metric not present → skip

            if not self._check(value, rule.operator, rule.threshold):
                continue

            # Fire
            alert = Alert(
                rule_name=rule.name,
                severity=rule.severity,
                message=rule.message or f"{rule.metric} {rule.operator} {rule.threshold} (got {value})",
                metric=rule.metric,
                current_value=value,
                threshold=rule.threshold,
                operator=rule.operator,
                timestamp=now,
            )
            fired.append(alert)
            self._last_fired[rule.name] = now

            # Dispatch
            for handler in self._handlers:
                try:
                    handler(alert)
                except Exception:
                    logger.exception("[Alerts] Handler failed for %s", rule.name)

            # Archive
            self._fired_history.append(alert)
            if len(self._fired_history) > 200:
                self._fired_history = self._fired_history[-100:]

        return fired

    # ── History ────────────────────────────────────────────────────

    def history(self, limit: int = 20) -> list[Alert]:
        """Return recent alert history (newest first)."""
        return list(reversed(self._fired_history[-limit:]))

    def clear_history(self) -> None:
        """Clear alert history."""
        self._fired_history.clear()

    # ── Static helpers ─────────────────────────────────────────────

    @staticmethod
    def _check(value: float, operator: str, threshold: float) -> bool:
        if operator == "lt":
            return value < threshold
        elif operator == "gt":
            return value > threshold
        elif operator == "eq":
            return value == threshold
        elif operator == "lte":
            return value <= threshold
        elif operator == "gte":
            return value >= threshold
        return False

    @staticmethod
    def _log_handler(alert: Alert) -> None:
        level = {
            "info": logging.INFO,
            "warning": logging.WARNING,
            "critical": logging.ERROR,
        }.get(alert.severity, logging.INFO)
        logger.log(level, "[ALERT %s] %s → %s (%.3f)",
                   alert.severity.upper(), alert.rule_name,
                   alert.message, alert.current_value)
