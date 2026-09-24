"""Deterministic agent dispatch with an auditable execution trace."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import monotonic
from types import MappingProxyType
from typing import Any, Callable, Mapping


@dataclass(frozen=True)
class AgentResult:
    value: Any
    metrics: dict[str, int | float | str | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class Agent:
    name: str
    requires: tuple[str, ...]
    run: Callable[[Mapping[str, Any]], AgentResult]


class Orchestrator:
    """Run specialist agents in dependency order and stop on the first failure."""

    def __init__(self, agents: list[Agent], on_event: Callable[[dict], None]):
        if not agents:
            raise ValueError('At least one agent is required')
        seen = set()
        for agent in agents:
            if not agent.name or agent.name in seen:
                raise ValueError(f'Duplicate or empty agent name: {agent.name!r}')
            if len(set(agent.requires)) != len(agent.requires):
                raise ValueError(f'Duplicate dependency for {agent.name}')
            missing = set(agent.requires) - seen
            if missing:
                raise ValueError(f'Unresolved dependencies for {agent.name}: {sorted(missing)}')
            seen.add(agent.name)
        self.agents = tuple(agents)
        self.on_event = on_event

    def execute(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for agent in self.agents:
            start = monotonic()
            self.on_event(dict(agent=agent.name, state='running', at=_now()))
            try:
                inputs = {name: results[name] for name in agent.requires}
                outcome = agent.run(MappingProxyType(inputs))
                if not isinstance(outcome, AgentResult):
                    raise TypeError(f'{agent.name} must return AgentResult')
                results[agent.name] = outcome.value
                self.on_event(dict(agent=agent.name, state='completed', at=_now(),
                                   duration_seconds=round(monotonic() - start, 3),
                                   metrics=outcome.metrics))
            except Exception as exc:
                self.on_event(dict(agent=agent.name, state='failed', at=_now(),
                                   duration_seconds=round(monotonic() - start, 3),
                                   error_type=type(exc).__name__))
                raise
        return results


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
