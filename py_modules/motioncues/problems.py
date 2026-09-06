"""A shared, bounded problem log.

The rule this enforces: **nothing fails silently, and nothing is reported
twice.**

Both the Decky backend and the overlay helper keep one of these.  Anything
that goes wrong - a sensor that will not open, an overlay window that cannot
be created, a setting that could not be saved - is recorded here with enough
context to act on, and surfaced to the panel.  When the log is empty the UI
shows nothing at all.

Two behaviours matter for keeping it honest rather than noisy:

* **Repeats are folded together.**  A sensor read failing 250 times a second
  is one problem with a count, not 250 entries.
* **Conditions that recover are withdrawn.**  ``resolve()`` removes an entry
  whose cause has demonstrably cleared - the sensor reopened, the window was
  created - so a transient startup failure does not sit in the UI forever
  claiming something is broken when it is not.  One-shot events that cannot
  "recover" stay until the user dismisses them.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List, Optional

ERROR = "error"
WARNING = "warning"

SEVERITIES = (ERROR, WARNING)

#: Plenty for diagnosis, bounded so a failing loop cannot grow without limit.
DEFAULT_LIMIT = 40


class Problem:
    __slots__ = ("key", "severity", "source", "title", "detail", "hint",
                 "first_seen", "last_seen", "count")

    def __init__(self, key: str, severity: str, source: str, title: str,
                 detail: str, hint: str) -> None:
        now = time.time()
        self.key = key
        self.severity = severity
        self.source = source
        self.title = title
        self.detail = detail
        self.hint = hint
        self.first_seen = now
        self.last_seen = now
        self.count = 1

    def as_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "severity": self.severity,
            "source": self.source,
            "title": self.title,
            "detail": self.detail,
            "hint": self.hint,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "count": self.count,
        }


class ProblemLog:
    """Thread-safe, de-duplicating, bounded."""

    def __init__(self, limit: int = DEFAULT_LIMIT) -> None:
        self._problems: Dict[str, Problem] = {}
        self._limit = limit
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def record(self, source: str, title: str, detail: str = "",
               severity: str = ERROR, hint: str = "",
               key: Optional[str] = None) -> Problem:
        """Record a failure.  Repeats of the same key are folded together."""

        if severity not in SEVERITIES:
            severity = ERROR
        problem_key = key or f"{source}:{title}"

        with self._lock:
            existing = self._problems.get(problem_key)
            if existing is not None:
                existing.count += 1
                existing.last_seen = time.time()
                # Keep the most recent detail: the latest failure is the one
                # worth showing.
                if detail:
                    existing.detail = detail
                existing.severity = severity
                return existing

            problem = Problem(problem_key, severity, source, title, detail, hint)
            self._problems[problem_key] = problem

            if len(self._problems) > self._limit:
                # Drop the oldest entry rather than the newest failure.
                oldest = min(self._problems.values(), key=lambda item: item.last_seen)
                self._problems.pop(oldest.key, None)
            return problem

    def resolve(self, source: str, title: str = "",
                key: Optional[str] = None) -> bool:
        """Withdraw a problem whose cause has demonstrably cleared."""

        problem_key = key or f"{source}:{title}"
        with self._lock:
            return self._problems.pop(problem_key, None) is not None

    def resolve_source(self, source: str) -> int:
        """Withdraw every problem from one subsystem."""

        with self._lock:
            keys = [key for key, problem in self._problems.items()
                    if problem.source == source]
            for key in keys:
                self._problems.pop(key, None)
            return len(keys)

    def clear(self, key: Optional[str] = None) -> int:
        """Dismiss one problem, or all of them."""

        with self._lock:
            if key is None:
                count = len(self._problems)
                self._problems.clear()
                return count
            return 1 if self._problems.pop(key, None) is not None else 0

    # ------------------------------------------------------------------
    @property
    def has_problems(self) -> bool:
        with self._lock:
            return bool(self._problems)

    def snapshot(self) -> List[Dict[str, Any]]:
        """Newest first, so the panel leads with what just broke."""

        with self._lock:
            problems = sorted(self._problems.values(),
                              key=lambda item: item.last_seen, reverse=True)
            return [problem.as_dict() for problem in problems]
