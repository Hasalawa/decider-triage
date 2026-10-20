"""Typed client for the Strands Decider "System One" HTTP API.

The server is started with ``strands-decider serve <model> --port 8099`` and exposes
``POST /v1/systemone``. A request carries one ``state`` (text) and a dict of named
questions; a response carries one typed answer per question. Three question types:

* ``Noul``   -- yes/no, answered as P(true) in 0..1
* ``Choice`` -- one of N named options, answered as a label plus a confidence
* ``Score``  -- a position on an ordered rubric, answered as an expected level index

This client only needs ``httpx``, so the agent code never imports torch.
"""

from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx

DEFAULT_URL = "http://127.0.0.1:8099"
ENDPOINT = "/v1/systemone"


class DeciderError(RuntimeError):
    """The decider could not be reached or returned something unusable."""


# --------------------------------------------------------------------------- questions


@dataclass(frozen=True)
class Noul:
    """Yes/no question. ``true`` / ``false`` optionally sharpen what each side means."""

    instructions: str
    true: str | None = None
    false: str | None = None

    def to_wire(self) -> dict:
        wire: dict = {"type": "noul", "instructions": self.instructions}
        criteria = {k: v for k, v in (("true", self.true), ("false", self.false)) if v}
        if criteria:
            wire["criteria"] = criteria
        return wire


@dataclass(frozen=True)
class Choice:
    """Pick one option. ``options`` maps option name -> description of that option."""

    instructions: str
    options: Mapping[str, str]

    def to_wire(self) -> dict:
        return {"type": "choice", "instructions": self.instructions, "criteria": dict(self.options)}


@dataclass(frozen=True)
class Score:
    """Rate on an ordered rubric. ``levels`` is ascending: index 0 is the low end."""

    instructions: str
    levels: tuple[str, ...]

    def to_wire(self) -> dict:
        return {"type": "score", "instructions": self.instructions, "criteria": list(self.levels)}


Question = Noul | Choice | Score


# ----------------------------------------------------------------------------- answers


@dataclass(frozen=True)
class NoulAnswer:
    probability: float  # P(true)

    @property
    def confidence(self) -> float:
        return abs(2 * self.probability - 1)


@dataclass(frozen=True)
class ChoiceAnswer:
    label: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoreAnswer:
    value: float  # expected level index, 0 .. len(levels) - 1
    confidence: float
    legend: dict[str, str] = field(default_factory=dict)


Answer = NoulAnswer | ChoiceAnswer | ScoreAnswer


@dataclass(frozen=True)
class Decision:
    """All answers for one ``ask`` call, plus timing."""

    answers: dict[str, Answer]
    latency_ms: float  # server-reported inference time (falls back to wall time)
    wall_ms: float  # client-measured round trip
    input_tokens: int = 0

    def _get(self, key: str, kind: type):
        answer = self.answers.get(key)
        if not isinstance(answer, kind):
            raise DeciderError(f"answer {key!r} is not a {kind.__name__}")
        return answer

    def noul(self, key: str) -> float:
        return self._get(key, NoulAnswer).probability

    def choice(self, key: str) -> ChoiceAnswer:
        return self._get(key, ChoiceAnswer)

    def score(self, key: str) -> ScoreAnswer:
        return self._get(key, ScoreAnswer)


def _parse_answer(key: str, raw: dict) -> Answer:
    try:
        kind = raw["type"]
        if kind == "noul":
            return NoulAnswer(probability=float(raw["noul"]))
        if kind == "choice":
            return ChoiceAnswer(
                label=str(raw["choice"]),
                confidence=float(raw["confidence"]),
                probabilities={str(k): float(v) for k, v in raw.get("probabilities", {}).items()},
            )
        if kind == "score":
            return ScoreAnswer(
                value=float(raw["score"]),
                confidence=float(raw["confidence"]),
                legend={str(k): str(v) for k, v in raw.get("legend", {}).items()},
            )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise DeciderError(f"malformed answer for {key!r}: {raw!r}") from exc
    raise DeciderError(f"unknown answer type for {key!r}: {raw!r}")


# ------------------------------------------------------------------------------ client


class DeciderClient:
    """Thin client. One instance is safe to share; it holds a pooled ``httpx.Client``."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        model: str | None = None,
        timeout: float | None = None,
        http: httpx.Client | None = None,
    ) -> None:
        if timeout is None:
            timeout = float(os.environ.get("STRANDS_DECIDER_TIMEOUT", "120"))
        base = (base_url or os.environ.get("STRANDS_DECIDER_URL") or DEFAULT_URL).rstrip("/")
        if base.endswith(ENDPOINT):
            base = base[: -len(ENDPOINT)]
        self.base_url = base
        self.model = model
        self._http = http or httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def health(self) -> dict:
        try:
            resp = self._http.get(f"{self.base_url}/health")
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise DeciderError(f"decider health check failed: {exc}") from exc

    def ask(self, state: str, questions: Mapping[str, Question]) -> Decision:
        if not state or not state.strip():
            raise DeciderError("state must not be empty")
        payload: dict = {
            "state": state,
            "questions": {name: q.to_wire() for name, q in questions.items()},
        }
        if self.model:
            payload["model"] = self.model

        started = time.perf_counter()
        try:
            resp = self._http.post(f"{self.base_url}{ENDPOINT}", json=payload)
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise DeciderError(f"decider returned {exc.response.status_code}: {detail}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise DeciderError(f"decider request failed: {exc}") from exc
        wall_ms = (time.perf_counter() - started) * 1000

        raw_answers = body.get("answers") if isinstance(body, dict) else None
        if not isinstance(raw_answers, dict):
            raise DeciderError(f"response has no 'answers': {str(body)[:200]}")
        answers = {name: _parse_answer(name, raw) for name, raw in raw_answers.items()}
        missing = set(questions) - set(answers)
        if missing:
            raise DeciderError(f"response is missing answers for {sorted(missing)}")

        usage = body.get("usage") or {}
        return Decision(
            answers=answers,
            latency_ms=float(body.get("latency_ms", wall_ms)),
            wall_ms=wall_ms,
            input_tokens=int(usage.get("input_tokens", 0)),
        )
