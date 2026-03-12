# CommuteWise

CommuteWise is an AI-powered commute planning agent that answers questions like:

- “When should I leave for the office if I want to arrive between 10 and 11?”
- “When should I leave for dinner with Mom?”
- “Should I leave now?”

This repository is **MVP-scoped** and intentionally interview-friendly: modular, testable, mock-first, and evaluation-minded.

## Repo layout

- `docs/`: product + engineering docs (start with `docs/design.md`)
- `src/`: Python package code
  - `src/schemas.py`: core typed schemas (Pydantic models)
  - `src/providers/`: provider interfaces (Calendar / Maps) and mock/real implementations (later)
- `tests/`: unit tests (start with schemas + deterministic logic)

## Development

Install dependencies:

```bash
python3 -m pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

## Running the CLI

- **Gemini planner (default)** — uses Gemini for natural-language intent parsing and then runs the deterministic orchestrator and recommendation engine:

```bash
python3 -m src.cli "When should I leave for the office between 10 and 11?"
```

Gemini is responsible only for **natural-language understanding**; all time math, ETA usage, and recommendation logic remain deterministic and tool-grounded as described in `docs/design.md`.

## Gemini API setup

To use the Gemini-backed planner end-to-end, you need:

- A Gemini API key from Google AI Studio.
- The Google Gen AI Python SDK installed.

### 1. Get an API key

1. Visit Google AI Studio (`https://aistudio.google.com/app/apikey`).
2. Create an API key (or use the default one that is created for you).

### 2. Store the key in your environment

Set an environment variable in your shell (replace with your real key):

```bash
export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
```

For a persistent setup (zsh):

```bash
echo 'export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"' >> ~/.zshrc
source ~/.zshrc
```

`GeminiClient` reads `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) at startup and raises a clear error if neither is set.

### 3. Install the Gemini Python client library

Install the Google Gen AI SDK in your environment:

```bash
python3 -m pip install google-genai
```

The default `GeminiClient` in `src/providers/gemini/client.py` is wired to:

- Construct `genai.Client(api_key=...)`.
- Call `models.generate_content` with:
  - `model="gemini-1.5-flash"` by default.
  - `response_mime_type="application/json"` and a **response schema** that mirrors `CommuteIntent`.
- Parse the JSON string from `response.text` into a Python `dict` for the planner.

Once this is configured, running:

```bash
python3 -m src.cli "When should I leave for dinner with Mom?"
```

will:

- Use Gemini to parse the natural-language query into a structured intent.
- Resolve destinations and deadlines via the calendar/maps providers.
- Compute and validate a recommendation deterministically.

### Failure modes (Gemini)

In the current CLI:

- If the Gemini API returns an error (e.g. invalid key, quota, network), the planner raises a `PlannerTransportError` and the CLI prints a concise “Planner error” message.
- If Gemini returns malformed or schema-incompatible JSON, the planner raises a `PlannerModelError`, which is also surfaced as a “Planner error” in the CLI.
- Maps/calendar errors (e.g. no known route) are handled separately and surfaced as generic “Error:” messages.
