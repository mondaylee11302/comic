from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Callable, Dict, Iterable


@dataclass
class AgentRetryMatrix:
    enabled: bool = True
    default_max_attempts: int = 1
    default_backoff_sec: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_sec: float = 8.0
    per_agent_max_attempts: Dict[str, int] = field(default_factory=dict)

    def attempts_for(self, agent_name: str) -> int:
        if not self.enabled:
            return 1
        n = int(self.per_agent_max_attempts.get(agent_name, self.default_max_attempts))
        return max(1, n)

    def backoff_for(self, attempt_index: int) -> float:
        # attempt_index is 1-based retry index (after first failure).
        sec = float(self.default_backoff_sec) * (float(self.backoff_multiplier) ** max(0, int(attempt_index) - 1))
        return max(0.0, min(sec, float(self.max_backoff_sec)))


def is_retryable_exception(exc: BaseException) -> bool:
    non_retryable = (ValueError, FileNotFoundError, PermissionError, NotImplementedError)
    if isinstance(exc, non_retryable):
        return False
    return True


def run_agents_with_retry(
    agents: Iterable,
    run_one: Callable[[object], None],
    log: Callable[[str], None],
    retry: AgentRetryMatrix | None = None,
) -> None:
    policy = retry or AgentRetryMatrix()
    for agent in agents:
        name = str(getattr(agent, "name", agent.__class__.__name__))
        max_attempts = policy.attempts_for(name)
        attempt = 1
        while True:
            log(f"agent_start={name} attempt={attempt}/{max_attempts}")
            try:
                run_one(agent)
                log(f"agent_done={name} attempt={attempt}/{max_attempts}")
                break
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                retryable = is_retryable_exception(exc)
                if (not retryable) or attempt >= max_attempts:
                    log(
                        f"agent_fail={name} attempt={attempt}/{max_attempts} "
                        f"retryable={retryable} error={exc.__class__.__name__}: {exc}"
                    )
                    raise
                sleep_s = policy.backoff_for(attempt)
                log(
                    f"agent_retry={name} attempt={attempt}/{max_attempts} "
                    f"sleep={sleep_s:.1f}s error={exc.__class__.__name__}: {exc}"
                )
                time.sleep(sleep_s)
                attempt += 1

