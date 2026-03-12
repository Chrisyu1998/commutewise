"""
CLI entrypoint (mock-first, Week 1).

Thin wrapper around the orchestrator: parse request with RuleBasedPlanner,
run SimpleOrchestrator, print a readable recommendation.

This Week 1 demo is intentionally minimal and interactive:
- If the calendar resolution is ambiguous, ask the user which event they mean.
- If arrival constraints are missing, ask the user what time they wish to arrive.

No Streamlit/UI yet.
"""

from __future__ import annotations

import argparse
import sys

from src.orchestrator import OrchestratorResult, SimpleOrchestrator
from src.planner import RuleBasedPlanner
from src.recommendation import RecommendationError
from src.schemas import CommuteRequest
from src.providers.maps import UnknownRouteError


def _print_recommendation(result: OrchestratorResult) -> None:
    rec = result.recommendation
    assert rec is not None
    print(f"Recommendation: leave at {rec.departure_time.strftime('%H:%M')}")
    print(f"Buffer: {rec.buffer_minutes:.0f} min")
    print(f"Confidence: {rec.confidence}")
    print()
    print(rec.explanation)
    if rec.backup_departure_time:
        print()
        print(f"Backup (safer): leave by {rec.backup_departure_time.strftime('%H:%M')}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="CommuteWise: when should I leave? (Week 1 minimal)"
    )
    parser.add_argument(
        "query",
        nargs="?",
        default="",
        help="Natural-language query, e.g. 'When should I leave for the office between 10 and 11?'",
    )
    args = parser.parse_args()
    query = (args.query or "").strip()
    if not query:
        # Minimal interactive mode when no CLI arg is provided.
        query = input("Ask CommuteWise: ").strip()
        if not query:
            return 0

    planner = RuleBasedPlanner()
    orchestrator = SimpleOrchestrator(planner=planner)

    # Week 1 demo loop: allow up to two follow-ups (clarification, then arrival time).
    # This keeps the CLI small while still demonstrating the full flow.
    for _ in range(3):
        request = CommuteRequest(query=query)
        try:
            result = orchestrator.run(request)
        except (ValueError, UnknownRouteError, RecommendationError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        if result.kind == "recommendation":
            _print_recommendation(result)
            return 0

        if result.kind == "clarification":
            print(result.clarification_message)
            reply = input("> ").strip()
            if not reply:
                return 0
            # Minimal approach: rerun using the user's reply as the event query.
            # The RuleBasedPlanner treats this as an event query unless it contains "office".
            query = reply
            continue

        if result.kind == "no_event_found":
            print(result.message)
            return 0

        if result.kind == "needs_arrival_info":
            print(result.message)
            reply = input("> ").strip()
            if not reply:
                return 0
            # Minimal approach: append the arrival constraint to the original query.
            # Example: "office" + "between 10 and 11".
            query = f"{query} {reply}".strip()
            continue

        return 1

    print("Error: too many follow-ups.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
