# CommuteWise Project Workflow

This document defines how to build and contribute to CommuteWise. Follow it when implementing features, refactoring, or reviewing code. It applies to both human contributors and AI-assisted development.

---

## Project: CommuteWise

### Purpose

Build an AI-powered commute planning agent that recommends **when a user should leave**, using:

- **Calendar context** — resolve destinations and deadlines from events
- **Live ETA** — real-time route data from a Maps provider
- **Historical commute retrieval** — hybrid RAG over past commute episodes
- **Deterministic recommendation logic** — departure-time computation with risk modes
- **Offline evaluation** — measurable metrics over a golden scenario dataset

### Project Constraints


| Constraint                                           | Meaning                                                                                                                                         |
| ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **MVP scope only**                                   | Do not build beyond what is needed for the 3-week MVP (see [design.md](design.md)).                                                             |
| **Python**                                           | Implementation language is Python.                                                                                                              |
| **Modular architecture**                             | Components (planner, providers, retriever, recommendation engine, etc.) are separate and swappable.                                             |
| **Mock providers first**                             | Implement and test with `MockCalendarProvider` and `MockMapsProvider` before integrating real APIs.                                             |
| **Deterministic logic for time math and validation** | All scheduling arithmetic, buffer calculation, and feasibility checks are deterministic code — not LLM output.                                  |
| **LLM only for**                                     | Intent parsing, ambiguity detection, context summarization, and response generation. Do not use the LLM for ETA, time math, or hard validation. |
| **Simple, testable, interview-friendly**             | Code should be easy to read, test, and discuss in an interview. Avoid unnecessary abstraction.                                                  |
| **Explicit schemas and typed models**                | Use Pydantic (or similar) and type hints; avoid untyped dicts for core data.                                                                    |
| **No premature optimization**                        | Optimize only when metrics or UX justify it.                                                                                                    |
| **No unnecessary infrastructure**                    | Do not add queues, workers, containers, or production infra that the MVP does not need.                                                         |


---

## Coding Standards

### Structure and Style

- **Clear folder structure** — e.g. `src/`, `tests/`, `docs/`; group by feature or layer, not by file type only.
- **Docstrings** — Add docstrings for modules, classes, and public functions (Google or NumPy style is fine).
- **Type hints** — Use type hints on function parameters and return values.
- **Reasonable file size** — Prefer smaller, focused files over large monoliths. If a file grows beyond ~200–300 lines, consider splitting.
- **Tests for core business logic** — Recommendation engine, validation, intent parsing (where deterministic), and retrieval logic should have unit tests. Mock external providers in tests.

### Process

- **No silent assumptions** — If something is deferred or unclear, add a `TODO:` (or `FIXME:`) with a short explanation. Do not assume behavior without documenting it.
- **Plan before multi-file edits** — Before editing multiple files, briefly explain:
  - What you are building or changing
  - Which files/components are affected
  - In what order you will implement
- **Summarize after implementation** — After a non-trivial change, provide a short summary with:
  1. **Files changed** — List of paths and one-line description per file.
  2. **What was implemented** — Concise description of the feature or fix.
  3. **Known limitations** — What is not done, or what could break in edge cases.
  4. **How to test** — Commands or steps to run tests or manually verify (e.g. `pytest tests/...`, or “run CLI with …”).

---

## Workflow Checklist

Use this when starting a new task or PR:

1. **Scope** — Confirm the change fits MVP scope and the [design doc](design.md).
2. **Plan** — If touching multiple files, write or state the plan (what, which files, order) before coding.
3. **Implement** — Follow coding standards; add TODOs for assumptions or deferred work.
4. **Test** — Add or update tests for core logic; ensure existing tests pass.
5. **Summarize** — Provide the four-part summary (files changed, what was implemented, known limitations, how to test).

---

## References

- [Design document](design.md) — Architecture, data flow, and implementation plan.
- [README](../README.md) — Project overview and setup (update as the repo grows).

