# CommuteWise: Engineering Design Document

**Author:** Chris Yu  
**Status:** Draft  
**Date:** March 7, 2026  
**Last updated:** March 11, 2026 — Provider package layout (`providers/calendar/`, `providers/maps/`); EventResolver under calendar; event→PlaceRef (destination helper).

---

## Table of Contents

1. [TL;DR](#1-tldr)
2. [Problem Statement](#2-problem-statement)
3. [Goals](#3-goals)
4. [Non-Goals](#4-non-goals)
5. [Requirements](#5-requirements)
6. [Proposed Solution](#6-proposed-solution)
7. [High-Level Architecture](#7-high-level-architecture)
8. [Core Design Decisions and Tradeoffs](#8-core-design-decisions-and-tradeoffs)
9. [Detailed Design](#9-detailed-design)
10. [Data Flow](#10-data-flow)
11. [Evaluation Plan](#11-evaluation-plan)
12. [Risks and Mitigations](#12-risks-and-mitigations)
13. [Implementation Plan](#13-implementation-plan)
14. [Success Metrics](#14-success-metrics)
15. [Post-MVP Roadmap](#15-post-mvp-roadmap)
16. [Final Recommendation](#16-final-recommendation)
17. [Appendix](#appendix)

---

## 1. TL;DR

CommuteWise is an AI-powered commute planning agent that answers natural-language queries like:

- *"When should I leave for the office if I want to arrive between 10 and 11?"*
- *"When should I leave for dinner with Mom?"*
- *"Should I leave now?"*

The system is built on five core pillars:

| Pillar | Description |
|--------|-------------|
| **Calendar grounding** | Resolves destinations and deadlines from calendar context |
| **Live travel data** | Fetches real-time ETAs via Maps API |
| **Historical retrieval** | Hybrid RAG over prior commute episodes |
| **Recommendation logic** | Deterministic departure-time computation with risk modes |
| **Offline evaluation** | Measurable metrics over a golden scenario dataset |

The MVP is scoped to 3 weeks of work and is intentionally designed to demonstrate strong AI product engineering signals relevant to: tool use, context engineering, retrieval, ranking, reliability, and evaluation.

---

## 2. Problem Statement

Deciding when to leave for an event today requires repeated manual checking of Maps and mental estimation of traffic risk and time buffers. This is inefficient because the optimal departure time depends on multiple contextual factors simultaneously:

- Destination and current route conditions
- Arrival deadline or target window
- Historical traffic variability on similar trips
- Event metadata (type, urgency, flexibility)
- User preference for risk tolerance vs. convenience

A useful AI system should answer not just *"how long is the drive"* but:

> **What is the best departure time given my goal, context, and uncertainty?**

This is a well-scoped project because it is:

- A real, recurring user problem
- Grounded in external tool APIs (not pure LLM inference)
- Naturally suited for retrieval and ranking
- Evaluable offline with measurable metrics
- Small enough to build a strong MVP in 3 weeks

---

## 3. Goals

### 3.1 Product Goals

- Recommend a specific departure time for a user commute query
- Support both recurring destinations and calendar-linked destinations
- Return a concise, grounded explanation for the recommendation
- Handle ambiguous inputs safely via targeted clarification
- Support configurable risk modes: **aggressive**, **balanced**, and **safest**

### 3.2 System Goals

- Demonstrate structured LLM-based intent parsing
- Demonstrate tool orchestration across Calendar and Maps providers
- Demonstrate hybrid retrieval over historical commute cases
- Demonstrate ranking and recommendation logic over multiple candidates
- Demonstrate deterministic guardrails around LLM outputs
- Demonstrate offline evaluation with measurable metrics

### 3.3 Project Goals

This project should signal the ability to build AI systems, not just LLM demos. Specifically, it should demonstrate:

- Context engineering
- Tool-grounded reasoning
- Retrieval and reranking
- Reliability-minded system design
- Evaluation-first iteration
- Good judgment on when to use models vs. deterministic logic

---

## 4. Non-Goals

The following are explicitly **out of scope** for the MVP:

- Training a custom traffic prediction model
- Fine-tuning the main LLM
- Mobile app development
- Multimodal inputs
- Large-scale production infrastructure
- Always-on background monitoring
- Multi-user support
- Long-term personalization
- MCP as the primary integration layer

These may be explored post-MVP.

---

## 5. Requirements

### 5.1 Functional Requirements

The system must:

- Parse natural-language commute queries into structured intent
- Resolve destination from one of: explicit text, default office location, or calendar event
- Retrieve current route and ETA information from a Maps provider
- Retrieve relevant historical commute cases via hybrid retrieval
- Produce one or more candidate departure recommendations
- Select a final recommendation based on user preference and risk mode
- Validate that the recommendation is feasible
- Return a grounded, concise explanation
- Request clarification when required information is missing or ambiguous

### 5.2 Non-Functional Requirements

| Property | Description |
|----------|-------------|
| **Reliable** | Avoid contradictory or unsafe scheduling outputs |
| **Grounded** | Rely on external tool APIs for non-language facts |
| **Explainable** | Surface the evidence behind every recommendation |
| **Testable** | Support offline replay with mock providers |
| **Modular** | Support swappable mock and real providers |
| **Scoped** | Realistically implementable in 3 weeks |

---

## 6. Proposed Solution

### 6.1 Summary

CommuteWise is a modular AI planning system that:

1. Parses a user request into structured intent
2. Resolves event and destination context from calendar
3. Queries Maps for live ETA
4. Retrieves similar historical commute cases
5. Computes candidate departure strategies
6. Validates the final recommendation
7. Generates a grounded, concise natural-language response

### 6.2 Why This Framing

This project is intentionally framed as a **planning-and-recommendation system**, not a traffic forecasting model. That is the right tradeoff because:

- The user value is a **recommendation**, not a raw prediction
- Model training is not necessary to demonstrate AI engineering skill (personal goal)
- This scope is feasible in 3 weeks

---

## 7. High-Level Architecture

```
┌─────────────────────┐
│    User Interface   │
│   CLI / Streamlit   │
└──────────┬──────────┘
           │
           ▼
┌──────────────────────────┐
│  Planner / Intent Parser │
│  · parse task            │
│  · extract slots         │
│  · detect ambiguity      │
└────────────┬─────────────┘
             │
             ▼
┌──────────────────────────┐
│  Orchestrator / State    │
│  Graph                   │
│  · manage workflow       │
│  · invoke tools          │
│  · handle branching      │
└──────┬───────────────────┘
       │              │
       ▼              ▼
┌────────────┐   ┌─────────────┐
│  Calendar  │   │  Maps / ETA │
│  Provider  │   │  Provider   │
└─────┬──────┘   └──────┬──────┘
      │                 │
      └────────┬─────────┘
               │
               ▼
       ┌───────────────┐
       │    History    │
       │   Retriever   │
       │  (Hybrid RAG) │
       └───────┬───────┘
               │
               ▼
       ┌───────────────┐
       │    Context    │
       │   Assembler   │
       └───────┬───────┘
               │
               ▼
       ┌───────────────┐
       │ Recommendation│
       │    Engine     │
       └───────┬───────┘
               │
               ▼
       ┌───────────────┐
       │   Guardrail / │
       │   Validator   │
       └───────┬───────┘
               │
               ▼
       ┌───────────────┐
       │   Response    │
       │   Generator   │
       └───────────────┘
```

---

## 8. Core Design Decisions and Tradeoffs

### 8.1 Why No Fine-Tuning

**Decision:** Do not fine-tune the main model for the MVP.

**Rationale:**

- Insufficient labeled data for meaningful fine-tuning
- Likely failure modes are system-level, not model-knowledge-level
- Prompt design, retrieval, schemas, and guardrails offer higher ROI

**Alternatives considered:**

- *Fine-tune intent parser* — could improve parsing consistency, but likely unnecessary with structured outputs and few-shot examples
- *Fine-tune response generator* — low value; explanation style is not the hardest problem

**Conclusion:** Fine-tuning is deferred unless evaluation reveals a narrow repeated error pattern that prompt and system changes cannot fix.

---

### 8.2 Why Prompt Engineering Is Included

**Decision:** Use prompt engineering in bounded, high-value parts of the system only.

| ✅ Good uses | ❌ Not used for |
|-------------|-----------------|
| Intent classification | Time arithmetic |
| Slot extraction | Route duration estimation |
| Ambiguity detection | Buffer calculations |
| Context summarization | Hard feasibility checks |
| Final explanation generation | — |
| Optional LLM judge prompt | — |

**Rationale:** This split demonstrates disciplined model usage — LLM for interpretation and synthesis, deterministic logic for correctness-sensitive computation.

---

### 8.3 Why Direct APIs Over MCP

**Decision:** Use direct provider wrappers for Google Calendar and Google Maps in the MVP.

**Rationale:** Direct APIs are better for MVP because they:

- Reduce implementation overhead
- Simplify mocking and offline testing
- Provide stronger control over request/response shapes
- Avoid unnecessary abstraction for a small number of tools

**Alternatives considered:**

| Option | Pros | Cons |
|--------|------|------|
| MCP-first approach | Agent platform flavor; standardized tool boundary | Extra complexity; lower ROI for a 3-week project; no material improvement to recommendation quality |

**Conclusion:** Use direct APIs for MVP. Keep tool contracts clean so an MCP layer can be added post-MVP.

---

### 8.4 Why Embeddings Are Included

**Decision:** Use embeddings selectively.

| ✅ Included for | ❌ Not included for |
|-----------------|---------------------|
| Fuzzy calendar event resolution | Deterministic route logic |
| Historical commute retrieval | Scheduling arithmetic |
| — | Validation |
| — | Every calendar operation |

**Rationale:** Embeddings are most valuable where semantic matching matters.

---

### 8.5 Why No Offline LLM Inference Over All Calendar Events

**Decision:** Prefetch and cache upcoming calendar events, but do not pre-run the LLM on every event.

**Rationale:**

- Weekly calendar size is small; query-time resolution is cheap
- Full precomputation adds complexity without strong benefit

**Chosen design:**

- Fetch the next 7 days of events
- Normalize and cache event metadata
- Optionally embed title / location / description
- Resolve the relevant event at query time

---

## 9. Detailed Design

### 9.1 Planner / Intent Parser

**Purpose:** Convert user input into structured intent and extracted fields.

**Example:**

*Input:* "When should I leave for dinner with Mom?"

```json
{
  "intent": "commute_plan",
  "origin_source": "home",
  "destination_source": "calendar_event",
  "origin_text": null,
  "destination_text": null,
  "event_query": "dinner with Mom",
  "arrival_time": null,
  "arrival_window_start": null,
  "arrival_window_end": null,
  "risk_mode": "balanced",
  "missing_fields": []
}
```

**Why LLM-based parsing:** Natural-language commute requests are fuzzy and under-specified. This is an appropriate use of a model with schema-constrained output. Rules-only approaches are brittle for fuzzy event names, implicit timing constraints, and leave-now questions.

**Timestamp convention:** Any timestamps produced by the planner (e.g. `arrival_time`, `arrival_window_start/end`) must be **timezone-aware** datetimes. The planner should not perform time arithmetic; it should only interpret user constraints into structured fields.

---

### 9.2 Orchestrator

**Purpose:** Manage the workflow and branch between tool calls, clarifications, and validation.

**Design:** State-machine / graph approach.

**Why this design:** The workflow naturally branches across several dimensions:

- Explicit destination vs. calendar event
- Single event match vs. ambiguous match
- Sufficient information vs. clarification needed
- Normal recommendation vs. low-confidence path

A graph/state-machine structure is significantly easier to debug and evaluate than a single long prompt.

**Missing arrival constraints:** If the parsed intent has no arrival time and no arrival window, the orchestrator does *not* invent a generic default (such as "arrive by end of next hour"). Week 1 behavior is:

- **Calendar-event destination**: default `arrival_time` to the **event start time** (i.e. interpret "leave for dentist" as "arrive by the appointment start").
- **Office/explicit destination**: return a structured “needs arrival info” result so the caller can prompt the user with a targeted question like **"What time do you wish to arrive?"** (e.g. “by 10:00” or “between 10 and 11”) and then re-run the flow with the user’s reply.

This keeps defaults deliberate and domain-specific (event start), while making missing constraints explicit for non-event commutes.

---

### 9.3 Calendar Provider

**Responsibilities:**

- Fetch upcoming events in a time window
- Normalize event metadata (from provider-specific shape to `CalendarEvent`)
- Resolve user free-text references to one or more candidate events

**Provider variants:** `MockCalendarProvider`, `GoogleCalendarProvider`

**Package layout:** Calendar provider code lives under **`src/providers/calendar/`**: `calendar.py` (protocol + MockCalendarProvider + `normalize_google_event`), `event_resolver.py` (EventResolver + lexical helpers). Tests live under **`tests/providers/calendar/`**. The top-level `src/providers/__init__.py` re-exports so `from src.providers import MockCalendarProvider` continues to work.

**Interface:**

- `get_events(start, end)` → `List[CalendarEvent]`: events that overlap the given window, sorted by start.
- `resolve_event(query, events)` → `EventResolutionResult`: candidates and scores for the query. `EventResolutionResult` has `candidates`, `scores`, and `needs_clarification` (true when more than one candidate). This allows the orchestrator to ask "Do you mean X or Y?" and re-call `resolve_event` with the user's reply to get a single event.

**Zero vs. multiple matches (Week 1 behavior):**

- **0 candidates**: the orchestrator returns a user-facing message indicating it **cannot find a related calendar event**, and asks the user to provide **date and location** (so the destination can be treated as explicit on retry, or the calendar time window can be widened).
- **2+ candidates**: the orchestrator returns a user-facing **disambiguation prompt** like **"Do you mean event X or event Y?"** (constructed from candidate titles) and waits for the user’s reply to re-run `resolve_event`.

**Shared resolution (EventResolver):**

- Resolution logic is implemented in a shared **EventResolver** component (`src/providers/calendar/event_resolver.py`). Both MockCalendarProvider and the future GoogleCalendarProvider delegate `resolve_event` to it (or to an injectable resolver), so behavior is consistent and testable. Week 2 can introduce an embedding-based resolver with the same contract without changing the provider interface.

**Event resolution strategy:**

1. Orchestrator calls `get_events(start, end)` to fetch candidates in the date window.
2. Orchestrator calls `resolve_event(intent.event_query, events)`.
3. If `result.needs_clarification` is true, surface a clarification question using candidate titles (e.g. "Do you mean Dinner with Mom or Dinner with Dad?"), then call `resolve_event(user_reply, events)` again to get a single event.
4. Week 2: optionally add embedding similarity inside the resolver; the return type and clarification flow stay the same.

**Mock and fixture data:**

- Mock uses local fixture JSON in **Google Calendar API list response shape** (`calendar#events` with `items[]`). Each item is a Google event resource (`summary`, `start`/`end` as `dateTime` or `date` + `timeZone`, `location`, `status`, etc.). Events are normalized via `normalize_google_event` to `CalendarEvent`; cancelled events are skipped. This keeps the mock realistic for future Google provider integration.

---

### 9.4 Maps Provider

**Responsibilities:**

- Return ETA for origin → destination
- Optionally return route metadata

**Provider variants:** `MockMapsProvider`, `GoogleMapsProvider`

**Package layout:** Maps provider code lives under **`src/providers/maps/`**: `maps.py` (protocol + MockMapsProvider + route fixture loading). Tests live under **`tests/providers/maps/`**. The top-level `src/providers/__init__.py` re-exports so `from src.providers import MockMapsProvider` continues to work.

**Data model:** Maps inputs/outputs use a `PlaceRef` object (label/address/provider ID) rather than raw strings. This keeps place identity stable across providers and historical records, which improves Week 2 retrieval and evaluation.

**Configuration and time helpers:** Default office/home locations are defined in `src/config.py`, and all timestamps flowing through providers should be normalized using helpers in `src/time_utils.py` to ensure they are timezone-aware.

**Why provider-based:** Maps data is deterministic and externally grounded. It must come from a provider, not from LLM inference.

---

### 9.4.1 Resolved Commute (Grounded State)

**Purpose:** Represent the grounded, post-orchestration commute that is ready for deterministic recommendation and validation.

**Why this exists:** `CommuteIntent` is interpretive (planner output) and may be ambiguous or incomplete. `ResolvedCommute` is the deterministic handoff point after resolving origin/destination to concrete `PlaceRef`s and attaching tool-grounded context (calendar event, maps ETA).

**Fields (conceptual):**

- `origin: PlaceRef`
- `destination: PlaceRef`
- `event: CalendarEvent | null` (when destination is calendar-derived)
- `route: RouteEstimate | null`
- `arrival_time | arrival_window_start | arrival_window_end` (timezone-aware)
- `risk_mode`

**Calendar-derived destination (event → PlaceRef):**

- When the destination comes from a calendar event, the orchestrator turns the chosen `CalendarEvent` into a `PlaceRef` using the helper **`event_to_place_ref(event)`** in `src/destination.py`. It sets `label = event.title`, `address = event.location`, and `provider_place_id = None` until Maps/Geocoding integration can resolve a stable place ID (Week 2+). The orchestrator owns the decision to call this when building `ResolvedCommute` for calendar_event destinations.

---

### 9.5 Historical Commute Store

**Purpose:** Store prior commute episodes for retrieval and replay.

**Example record:**

```json
{
  "origin": {
    "label": "Home",
    "address": null,
    "provider_place_id": null
  },
  "destination": {
    "label": "Sunnyvale Office",
    "address": null,
    "provider_place_id": null
  },
  "event_type": "office_commute",
  "planned_arrival_time": "2026-02-12T09:30:00-08:00",
  "departure_time": "2026-02-12T08:42:00-08:00",
  "arrival_time": null,
  "actual_duration_min": 41,
  "late": false,
  "condition_tags": ["rush_hour", "light_rain"],
  "notes": "Traffic heavier than usual near final exit"
}
```

**Timestamp convention:** Historical timestamps are stored as **timezone-aware** datetimes (e.g. ISO-8601 with offset). This avoids ambiguity in retrieval features (weekday/time-band) and offline evaluation.

**Storage design:**

- Structured storage for metadata (hard constraint filtering)
- Vector store for semantic retrieval (fuzzy similarity)

---

### 9.6 History Retriever (Hybrid RAG)

**Purpose:** Retrieve similar commute cases that inform the current recommendation.

**Pipeline:**

1. Metadata filtering (hard constraints)
2. Vector similarity retrieval
3. Reranking
4. Select top 3–5 cases

**Reranking features:**

| Feature | Weight |
|---------|--------|
| Route match | High |
| Weekday similarity | Medium |
| Time-band similarity | Medium |
| Condition similarity | Medium |
| Recency | Low |
| Same event type | Low |

**Why hybrid retrieval:** Metadata-only is too rigid. Vector-only is too noisy. Hybrid retrieval is the best tradeoff for this use case.

---

### 9.7 Context Assembler

**Purpose:** Assemble the minimum useful context for the recommendation stage.

**Inputs:**

- Parsed request
- Resolved event info
- Maps ETA
- Retrieved commute cases
- Risk mode
- Uncertainty notes

**Why explicit assembly:** This avoids passing raw tool output dumps into the model and keeps the system inspectable and debuggable.

---

### 9.8 Recommendation Engine

**Purpose:** Compute departure time recommendations.

**Output candidates:**

| Option | Strategy |
|--------|----------|
| **Aggressive** | Minimal buffer; optimistic traffic assumption |
| **Balanced** | Moderate historical adjustment + moderate buffer |
| **Safest** | Stronger historical adjustment + larger buffer |

**Design:** Fully deterministic logic.

**Why deterministic:** Departure-time recommendation is correctness-sensitive. The system must not rely on free-form LLM reasoning for scheduling arithmetic.

**Arrival window rules:**

- **Target within window (mode-specific):** Aggressive aims near the end of the window (`window_end - 5` minutes), clamped to `window_start` if the window is shorter than 5 minutes. Balanced aims at the middle; safest aims at `window_start`.
- **Validity (asymmetric):** For a candidate to be valid with an arrival window, the implied arrival (departure + ETA) must lie in **\[window_start − buffer, window_end\]**. Arriving up to `buffer` minutes early is allowed (so the safest candidate that targets `window_start` and actually arrives at `window_start − buffer` is valid). Arrival after `window_end` is never allowed.

---

### 9.9 Guardrail / Validator

**Purpose:** Ensure the recommendation is feasible and internally consistent.

**Checks performed:**

- Arrival falls before deadline or within the target window
- Minimum buffer threshold is met
- Destination resolution confidence is sufficient
- No key fields are missing
- Explanation text does not contradict structured facts

**Design:** Deterministic validation first; optional LLM judge second.

**Why this design:** Hard constraints must be machine-checked, not model-guessed.

---

### 9.10 Response Generator

**Purpose:** Produce a concise, grounded user-facing answer.

**Example output:**

> **Recommendation:** Leave at 5:10 PM.  
> **Why:** Current ETA is 34 minutes, and similar Friday evening trips to this area typically run 8–12 minutes longer.  
> **Confidence:** Medium.  
> **Backup option:** If you want lower lateness risk, leave by 5:00 PM.

**Why use an LLM here:** The facts are already fixed by the upstream components, so the model is only being used for readability and polish — a low-risk, high-value application.

---

## 10. Data Flow

### 10.1 Office Commute

*"When should I leave for the office if I want to arrive between 10 and 11?"*

1. Planner extracts office destination + arrival window
2. Orchestrator resolves office config
3. Maps provider returns live ETA
4. History retriever returns similar office commute cases
5. Recommendation engine computes candidates
6. Validator checks feasibility
7. Response generator returns final answer

### 10.2 Calendar Event

*"When should I leave for dinner with Mom?"*

1. Planner identifies calendar event query (`event_query` e.g. "dinner with Mom").
2. Orchestrator calls calendar provider `get_events(start, end)`, then `resolve_event(event_query, events)`.
3. If there are **0 candidates**, return a message: **cannot find a related calendar event** and ask the user for **date and location** (then retry as explicit destination or with a wider calendar window).
4. If `EventResolutionResult.needs_clarification` is true (**2+ candidates**), return a message like **"Do you mean event X or event Y?"** and wait for the user’s reply to re-run event resolution.
5. If `EventResolutionResult.needs_clarification` is false and there is **exactly 1** candidate, use that event; set destination via `event_to_place_ref(event)`.
6. If the user did **not** provide an arrival time/window, default `arrival_time` to the **event start time**.
7. Maps provider returns route ETA for that destination.
8. History retriever returns similar commute cases.
9. Recommendation engine computes recommendation.
10. Validator checks feasibility.
11. Response generator returns final answer.

### 10.3 Clarification Flow

*"When should I leave for lunch?"*

1. Planner identifies likely event-based commute request.
2. Orchestrator calls `get_events`, then `resolve_event("lunch", events)`; result has multiple candidates and `needs_clarification` true.
3. System surfaces a targeted clarification question using candidate titles, e.g. "Do you mean Lunch with Sarah or Lunch with Alex?"
4. User replies (e.g. "Sarah" or "the first one").
5. Orchestrator calls `resolve_event(user_reply, events)` again; result now has a single candidate.
6. Normal flow resumes from step 3 of the Calendar Event flow (destination = `event_to_place_ref(chosen_event)`, then Maps, etc.).

### 10.4 No Calendar Match Flow

*"When should I leave for dinner with Mom?" (but the calendar has no matching event, or the query is too vague)*

1. Planner identifies `destination_source="calendar_event"` and sets `event_query`.
2. Orchestrator calls `get_events` and `resolve_event(event_query, events)`.
3. If the result has **0 candidates**, the system returns: **"We cannot find a related calendar event. You can let me know the date and location."**
4. The user provides a **date/time and location**, and the caller re-runs the flow using either:
   - an explicit destination (address/label), or
   - an updated `event_query` and/or a wider calendar time window.

---

## 11. Evaluation Plan

### 11.1 Why Evaluation Matters

Without evaluation, this project risks looking like a demo. With evaluation, it demonstrates real AI engineering maturity and provides a principled basis for iteration.

### 11.2 Golden Dataset

**Target size:** 40–60 scenarios

**Scenario categories:**

| Category | Description |
|----------|-------------|
| Office commute | Standard weekday office trip |
| Dinner event | Calendar-linked evening event |
| Leave-now flow | Real-time departure decision |
| Ambiguous event name | Multiple calendar matches |
| Missing location | Destination requires clarification |
| Tight arrival window | High-stakes deadline |
| Short-trip edge case | Very short travel time |
| Conflicting history vs. live ETA | Historical and live data disagree |
| Fuzzy event phrasing | Informal or ambiguous event references |

**Each scenario includes:**

- User query
- Mock calendar data
- Mock Maps response
- Mock history data
- Expected event resolution
- Acceptable leave-time range
- Expected clarification behavior (if applicable)

### 11.3 Metrics

**Product metrics:**

| Metric | Description |
|--------|-------------|
| Task success rate | End-to-end correct recommendation |
| Destination resolution accuracy | Correct event/location resolved |
| Clarification correctness | Right question asked at right time |
| Feasible-arrival rate | Recommendation produces on-time arrival |
| Late-arrival rate | Recommendation results in lateness |

**Quantitative metrics:**

| Metric | Description |
|--------|-------------|
| MAE vs. reference leave time | Mean absolute error in minutes |
| Minimum buffer compliance | % of recommendations meeting minimum buffer |
| Average buffer | Mean buffer provided across scenarios |

**System metrics:**

- Invalid structured output rate
- End-to-end latency (P50, P95)

### 11.4 Ablations

Evaluate each configuration sequentially to measure component contribution:

1. Live ETA only (baseline)
2. Live ETA + historical retrieval
3. Reranking
4. Guardrails
5. Confidence and explanation improvements

**Why:** Ablations prove which components actually contribute to recommendation quality — critical for demonstrating engineering rigor.

---

## 12. Risks and Mitigations

| Risk | Mitigation |
|------|-------------|
| Event resolution quality is weak | Use layered matching: date filters → shared EventResolver (lexical, then optionally embeddings) → clarification when `EventResolutionResult.needs_clarification`; re-call `resolve_event` with user reply to disambiguate. |
| Retrieval adds limited value | Run ablations; improve dataset realism and reranking features |
| Real APIs slow down the build | Build with mocks first; treat real integration as Week 3 polish |
| Project looks too rules-based | Emphasize planner, retrieval, clarification, explanation generation, and eval results |
| Scope expands too much | Keep MVP focused on office commute, event commute, leave-now, retrieval, and evaluation |

---

## 13. Implementation Plan

### Week 1 — Build the Spine

**Goal:** Get a full end-to-end flow working with mock providers.

**Tasks:**

- Create repo structure and define schemas (including `EventResolutionResult` for resolution + clarification)
- Build planner / intent parser
- Build MockCalendarProvider (get_events, resolve_event → EventResolutionResult) and MockMapsProvider under `src/providers/calendar/` and `src/providers/maps/` respectively
- Build shared EventResolver in `src/providers/calendar/event_resolver.py` (lexical matching; used by mock and future Google provider)
- Add `event_to_place_ref` in `src/destination.py` for calendar-derived destination → PlaceRef
- Define office default config
- Implement orchestrator
- Implement recommendation engine v1
- Build CLI or Streamlit demo

**Exit criteria:**

- Office commute flow works end-to-end
- Simple event commute flow works; ambiguous queries return EventResolutionResult with needs_clarification; clarification flow (ask "Do you mean X or Y?", re-resolve on reply) is supported
- Demo exists

### Week 2 — Add Intelligence

**Goal:** Make the system context-aware and more robust.

**Tasks:**

- Define commute-history schema
- Build historical dataset
- Integrate embeddings (e.g. for EventResolver or historical retrieval)
- Build hybrid retrieval pipeline
- Add reranking
- Implement clarification logic in orchestrator (use EventResolutionResult.needs_clarification, prompt "Do you mean X or Y?", re-call resolve_event with user reply; optionally add confidence thresholds)
- Improve explanation generation

**Exit criteria:**

- System retrieves relevant commute history
- Ambiguous calendar queries trigger clarification using the existing EventResolutionResult contract
- Explanation cites retrieved patterns

### Week 3 — Add Quality and Polish

**Goal:** Produce measurable results and make the project portfolio-ready.

**Tasks:**

- Create golden scenario dataset
- Build eval runner and compute metrics
- Implement guardrails
- Add confidence scoring
- Optionally integrate real Google Calendar
- Polish README and demo materials

**Exit criteria:**

- Offline evaluation results exist
- Ablation comparisons exist
- Demo is polished enough for transfer discussions

---

## 14. Success Metrics

The MVP is successful if:

- It completes the main office and event commute flows end-to-end
- It safely handles ambiguous inputs through targeted clarification
- It shows measurable improvement over a live-ETA-only baseline
- It has a clean, explainable, and defensible architecture
- It demonstrates more than API calling — system design, retrieval, and eval rigor

---

## 15. Post-MVP Roadmap

| Phase | Capability |
|-------|------------|
| Real integration polish | Richer OAuth flow, route alternatives, route matrix support |
| MCP layer | Expose tool layer through MCP for broader agent platform use |
| Personalization | Learn default risk preference; adapt buffer strategy from behavior |
| Proactive assistance | "Leave by 5:05 PM" push notifications; traffic worsening warnings |
| Probabilistic modeling | Formally estimate lateness risk; replace heuristics with learned distributions |
| Feedback loop | Collect whether recommendations were followed; improve eval and ranking |

---

## 16. Final Recommendation

CommuteWise should be built as a **context-aware planning agent** — not a traffic-prediction research project and not a thin LLM wrapper.

The strongest version of this project clearly demonstrates:

- Tool-grounded reasoning
- Hybrid retrieval
- Ranking and decision logic
- Deterministic safety checks
- Evaluation-driven improvement

That is the version most likely to support a successful internal transfer into AI-related teams.

---

## Appendix

### A. Short Pitch

CommuteWise is an AI commute planning agent that answers *"When should I leave?"* by grounding to calendar context, live route data, and retrieved historical commute cases. It uses structured tool-calling, hybrid retrieval, reranking, deterministic validation, and offline evaluation to generate explainable recommendations under uncertainty.

### B. Suggested Resume Bullet

Built an LLM-powered commute planning agent that resolves destinations from calendar events, combines live ETA with retrieved historical commute cases, and recommends departure times under uncertainty using structured tool-calling, hybrid retrieval, reranking, deterministic guardrails, and an offline evaluation framework.
