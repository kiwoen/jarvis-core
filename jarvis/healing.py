"""Self-healing engine — automatic corrective actions triggered by alerts.

When AlertManager fires an alert, the HealingEngine matches it against
registered healing actions and executes them (with cooldown to prevent
runaway loops). Integrates into Scheduler.tick for autonomous operation.

Usage:
    from jarvis.healing import HealingEngine, HealingAction
    from jarvis.alerts import AlertManager

    mgr = AlertManager()
    healer = HealingEngine()

    healer.register(HealingAction(
        name="restart_scheduler_if_down",
        alert_rule="scheduler_down",
        action=restart_procedure,
    ))

    # Auto-evaluate after alert check:
    for alert in fired_alerts:
        healer.handle(alert)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# Types
# ══════════════════════════════════════════════════════════════════


@dataclass
class HealingAction:
    """A corrective action triggered by a specific alert rule.

    Args:
        name: Unique name for this healing action.
        alert_rule: Name of the AlertRule that triggers this action.
        action: Zero-arg callable executed when triggered.
        cooldown_seconds: Minimum time between consecutive executions.
        max_attempts: Maximum total executions (0 = unlimited).
        enabled: Whether this action can fire.
    """

    name: str
    alert_rule: str
    action: Callable[[], Any]
    cooldown_seconds: float = 300.0
    max_attempts: int = 10
    enabled: bool = True
    tags: list[str] = field(default_factory=list)


@dataclass
class HealingRecord:
    """Record of a healing action execution."""

    action_name: str
    alert_rule: str
    timestamp: float
    success: bool
    error: str = ""


# ══════════════════════════════════════════════════════════════════
# Engine
# ══════════════════════════════════════════════════════════════════


class HealingEngine:
    """Matches fired alerts to healing actions and executes them."""

    def __init__(self) -> None:
        self._actions: dict[str, HealingAction] = {}
        self._history: list[HealingRecord] = []
        self._last_triggered: dict[str, float] = {}  # action_name → timestamp
        self._attempt_counts: dict[str, int] = {}     # action_name → count

    # ── Registration ────────────────────────────────────────────────

    def register(self, action: HealingAction) -> None:
        """Register a healing action."""
        self._actions[action.name] = action
        logger.debug("[Healing] Action registered: %s → alert '%s'",
                     action.name, action.alert_rule)

    def unregister(self, name: str) -> bool:
        """Remove a healing action by name."""
        if name in self._actions:
            del self._actions[name]
            self._last_triggered.pop(name, None)
            self._attempt_counts.pop(name, None)
            return True
        return False

    def get_action(self, name: str) -> Optional[HealingAction]:
        """Get a healing action by name (returns a copy)."""
        a = self._actions.get(name)
        if a is None:
            return None
        return HealingAction(
            name=a.name, alert_rule=a.alert_rule, action=a.action,
            cooldown_seconds=a.cooldown_seconds, max_attempts=a.max_attempts,
            enabled=a.enabled, tags=list(a.tags),
        )

    def list_actions(self) -> list[HealingAction]:
        """List all registered actions (copies)."""
        return [self.get_action(name) for name in self._actions]

    # ── Triggering ──────────────────────────────────────────────────

    def handle(self, alert_rule_name: str) -> list[HealingRecord]:
        """Check and execute all matching healing actions for a fired alert rule.

        Returns a list of HealingRecord for each action executed (may be empty).
        """
        now = time.time()
        records: list[HealingRecord] = []

        for action in self._actions.values():
            if not action.enabled:
                continue
            if action.alert_rule != alert_rule_name:
                continue

            # Cooldown check
            last = self._last_triggered.get(action.name, 0)
            if now - last < action.cooldown_seconds:
                logger.debug("[Healing] '%s' on cooldown (%.0fs remaining)",
                             action.name, action.cooldown_seconds - (now - last))
                continue

            # Attempt limit check
            attempts = self._attempt_counts.get(action.name, 0)
            if action.max_attempts > 0 and attempts >= action.max_attempts:
                logger.debug("[Healing] '%s' exhausted (%d/%d attempts)",
                             action.name, attempts, action.max_attempts)
                continue

            # Execute
            logger.info("[Healing] Triggering '%s' for alert '%s'",
                        action.name, alert_rule_name)
            self._last_triggered[action.name] = now
            self._attempt_counts[action.name] = attempts + 1

            success = True
            error_msg = ""
            try:
                action.action()
            except Exception as e:
                success = False
                error_msg = str(e)
                logger.exception("[Healing] Action '%s' failed: %s",
                                 action.name, e)

            record = HealingRecord(
                action_name=action.name,
                alert_rule=alert_rule_name,
                timestamp=now,
                success=success,
                error=error_msg,
            )
            self._history.append(record)
            records.append(record)

        # Trim history if too large
        if len(self._history) > 200:
            self._history = self._history[-100:]

        return records

    def handle_batch(self, fired_alert_rule_names: list[str]) -> list[HealingRecord]:
        """Process multiple fired alert rules in one pass."""
        records: list[HealingRecord] = []
        for rule_name in fired_alert_rule_names:
            records.extend(self.handle(rule_name))
        return records

    # ── History ─────────────────────────────────────────────────────

    def history(self, limit: int = 20) -> list[HealingRecord]:
        """Return recent healing records (newest first)."""
        return list(reversed(self._history[-limit:]))

    def clear_history(self) -> None:
        """Clear healing history."""
        self._history.clear()

    def reset_attempts(self, name: str = "") -> None:
        """Reset attempt counters. If name is empty, reset all."""
        if name:
            self._attempt_counts.pop(name, None)
            self._last_triggered.pop(name, None)
        else:
            self._attempt_counts.clear()
            self._last_triggered.clear()
