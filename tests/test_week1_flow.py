"""
Integration-style tests for the Week 1 CLI flow.

These tests keep things lightweight and mock-based by exercising `src.cli.main()`
while stubbing the orchestrator behavior (and user input) to validate the
follow-up loop semantics (clarification + arrival questions).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterable, List, Optional

from zoneinfo import ZoneInfo

from src.config import DEFAULT_TIMEZONE
from src.orchestrator import OrchestratorResult
from src.schemas import CalendarEvent, CommuteRequest, Recommendation


def _dt(y: int, m: int, d: int, hh: int, mm: int) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=ZoneInfo(DEFAULT_TIMEZONE))


def _rec(hh: int = 9, mm: int = 45) -> Recommendation:
    return Recommendation(
        departure_time=_dt(2026, 3, 12, hh, mm),
        buffer_minutes=10.0,
        confidence="medium",
        explanation="Test recommendation.",
        backup_departure_time=None,
    )


def _event(title: str) -> CalendarEvent:
    return CalendarEvent(
        id=title.lower().replace(" ", "-"),
        title=title,
        start=_dt(2026, 3, 12, 12, 0),
        end=_dt(2026, 3, 12, 13, 0),
        location="Somewhere",
        timezone=DEFAULT_TIMEZONE,
    )


@dataclass
class _FakeOrchestrator:
    responder: Callable[[str], OrchestratorResult]
    seen_queries: List[str]

    def run(self, request: CommuteRequest) -> OrchestratorResult:
        self.seen_queries.append(request.query)
        return self.responder(request.query)


def _patch_cli(monkeypatch, fake: _FakeOrchestrator) -> None:
    import src.cli as cli

    monkeypatch.setattr(cli, "RuleBasedPlanner", lambda *args, **kwargs: object())
    monkeypatch.setattr(cli, "SimpleOrchestrator", lambda *args, **kwargs: fake)


def _patch_argv(monkeypatch, query: str) -> None:
    monkeypatch.setattr("sys.argv", ["commutewise", query])


def _patch_inputs(monkeypatch, replies: Iterable[str]) -> None:
    it = iter(replies)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(it))


def test_week1_cli_office_commute_flow_prints_recommendation(monkeypatch, capsys) -> None:
    import src.cli as cli

    seen: list[str] = []

    def responder(q: str) -> OrchestratorResult:
        assert "office" in q.lower()
        return OrchestratorResult(kind="recommendation", recommendation=_rec())

    fake = _FakeOrchestrator(responder=responder, seen_queries=seen)
    _patch_cli(monkeypatch, fake)
    _patch_argv(monkeypatch, "When should I leave for the office between 10 and 11?")

    code = cli.main()
    out = capsys.readouterr().out

    assert code == 0
    assert seen == ["When should I leave for the office between 10 and 11?"]
    assert "Recommendation: leave at 09:45" in out
    assert "Buffer:" in out
    assert "Confidence:" in out


def test_week1_cli_event_commute_flow_prints_recommendation(monkeypatch, capsys) -> None:
    import src.cli as cli

    seen: list[str] = []

    def responder(q: str) -> OrchestratorResult:
        assert "dentist" in q.lower()
        return OrchestratorResult(kind="recommendation", recommendation=_rec(8, 15))

    fake = _FakeOrchestrator(responder=responder, seen_queries=seen)
    _patch_cli(monkeypatch, fake)
    _patch_argv(monkeypatch, "When should I leave for dentist between 10 and 11?")

    code = cli.main()
    out = capsys.readouterr().out

    assert code == 0
    assert seen == ["When should I leave for dentist between 10 and 11?"]
    assert "Recommendation: leave at 08:15" in out


def test_week1_cli_missing_event_case_prints_message_and_exits(monkeypatch, capsys) -> None:
    import src.cli as cli

    seen: list[str] = []

    def responder(q: str) -> OrchestratorResult:
        return OrchestratorResult(kind="no_event_found", message="No matching event found.")

    fake = _FakeOrchestrator(responder=responder, seen_queries=seen)
    _patch_cli(monkeypatch, fake)
    _patch_argv(monkeypatch, "When should I leave for my nonexistent meeting?")

    code = cli.main()
    out = capsys.readouterr().out

    assert code == 0
    assert seen == ["When should I leave for my nonexistent meeting?"]
    assert "No matching event found." in out


def test_week1_cli_ambiguous_event_case_followed_by_disambiguation(monkeypatch, capsys) -> None:
    import src.cli as cli

    base_query = "When should I leave for lunch?"
    seen: list[str] = []
    sarah = _event("Lunch with Sarah")
    alex = _event("Lunch with Alex")

    def responder(q: str) -> OrchestratorResult:
        if q == base_query:
            return OrchestratorResult(
                kind="clarification",
                clarification_candidates=[sarah, alex],
                clarification_message="Do you mean Lunch with Sarah or Lunch with Alex?",
            )
        if q == f"{base_query} Sarah":
            return OrchestratorResult(kind="recommendation", recommendation=_rec(11, 5))
        raise AssertionError(f"Unexpected query: {q}")

    fake = _FakeOrchestrator(responder=responder, seen_queries=seen)
    _patch_cli(monkeypatch, fake)
    _patch_argv(monkeypatch, base_query)
    _patch_inputs(monkeypatch, ["Sarah"])

    code = cli.main()
    out = capsys.readouterr().out

    assert code == 0
    assert seen == [base_query, f"{base_query} Sarah"]
    assert "Do you mean Lunch with Sarah or Lunch with Alex?" in out
    assert "Recommendation: leave at 11:05" in out


def test_week1_cli_needs_arrival_info_followed_by_user_reply(monkeypatch, capsys) -> None:
    import src.cli as cli

    base_query = "When should I leave for the office?"
    seen: list[str] = []

    def responder(q: str) -> OrchestratorResult:
        if q == base_query:
            return OrchestratorResult(
                kind="needs_arrival_info",
                message="What time do you wish to arrive?",
            )
        if q == f"{base_query} between 10 and 11":
            return OrchestratorResult(kind="recommendation", recommendation=_rec())
        raise AssertionError(f"Unexpected query: {q}")

    fake = _FakeOrchestrator(responder=responder, seen_queries=seen)
    _patch_cli(monkeypatch, fake)
    _patch_argv(monkeypatch, base_query)
    _patch_inputs(monkeypatch, ["between 10 and 11"])

    code = cli.main()
    out = capsys.readouterr().out

    assert code == 0
    assert seen == [base_query, f"{base_query} between 10 and 11"]
    assert "What time do you wish to arrive?" in out
    assert "Recommendation: leave at 09:45" in out

