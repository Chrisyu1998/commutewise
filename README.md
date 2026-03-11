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
