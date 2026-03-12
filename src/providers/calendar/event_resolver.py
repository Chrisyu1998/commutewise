"""
Shared event resolution logic for calendar providers.

Both MockCalendarProvider and future GoogleCalendarProvider (and any
embedding-based resolver in Week 2) can use this component so resolution
behavior is consistent and testable. The provider fetches events; the resolver
scores and ranks them against a user query.
"""

from __future__ import annotations

from typing import List, Sequence

from src.schemas import CalendarEvent, EventResolutionResult


_STOPWORDS = {
    # Very small set for Week 1 lexical matching.
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
}


def tokenize(text: str) -> List[str]:
    """Lowercase and split on non-alphanumeric; filter out empty tokens and stopwords."""
    normalized = (text or "").lower().strip()
    tokens = []
    for word in normalized.split():
        cleaned = "".join(c for c in word if c.isalnum())
        if cleaned and cleaned not in _STOPWORDS:
            tokens.append(cleaned)
    return tokens


def match_score(query_tokens: List[str], event: CalendarEvent) -> int:
    """
    Number of query tokens that appear in the event's title or location.

    Simple lexical match for Week 1; no embeddings. Used to rank and filter candidates.
    """
    searchable = f"{event.title} {event.location or ''}".lower()
    score = 0
    for token in query_tokens:
        if token in searchable:
            score += 1
    return score


class EventResolver:
    """
    Resolves a free-text query to one or more calendar events from a candidate list.

    Returns EventResolutionResult with candidates and scores so the orchestrator
    can ask "Do you mean X or Y?" when needs_clarification is True, then call
    resolve again with the user's reply to get a single event.
    """

    def resolve(
        self,
        query: str,
        events: Sequence[CalendarEvent],
    ) -> EventResolutionResult:
        """
        Return matching events and their scores, sorted by score descending then start.

        When multiple events match (e.g. "lunch" → two lunch events), the result
        includes all of them so the caller can ask the user to disambiguate.
        """
        if not query or not events:
            return EventResolutionResult(candidates=[], scores=[])
        tokens = tokenize(query)
        if not tokens:
            return EventResolutionResult(candidates=[], scores=[])
        scored: List[tuple[int, CalendarEvent]] = []
        for ev in events:
            score = match_score(tokens, ev)
            if score > 0:
                scored.append((score, ev))
        scored.sort(key=lambda p: (-p[0], p[1].start))
        candidates = [ev for _, ev in scored]
        scores = [float(s) for s, _ in scored]
        return EventResolutionResult(candidates=candidates, scores=scores)
