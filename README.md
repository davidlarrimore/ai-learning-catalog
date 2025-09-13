# Training Processing

Tools to enrich training course metadata from a CSV by calling the OpenAI API. Given an `input.csv` with at least `Provider` and `Link`, the scripts generate or refine fields and append standardized rows to `output.csv`.

## Requirements
- Python 3.11+ (tested with 3.13)
- `pip install -r requirements.txt`
- OpenAI API key

## Setup
1. Create a virtual environment (recommended) and install deps:
   - `python -m venv .venv && source .venv/bin/activate`
   - `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`. Adjust other settings as needed.

## CSVs
- `input.csv`: must include headers `Provider` and `Link`. Additional columns are ignored unless a script normalizes them.
- `output.csv`: script output; created if missing. Existing rows are respected (resume by skipping existing links) unless you set `CLEAR_OUTPUT_FILE=1`.

## Scripts
- `app.py`: Main end‑to‑end processor. Calls the OpenAI Responses API (or falls back) to fill all required fields using a strict JSON schema, then appends a canonicalized row to `output.csv`.
- `description.py`: Validates whether a Summary is meaningful; if not, generates a new concise Summary and writes the row.
- `difficulty.py`: Determines Difficulty (Easy/Moderate/Intense) from available info and writes the row.
- `length.py`: Estimates/sets the Length field (rounded hours) and writes the row.
- `skilllevel.py`: Determines Skill Level (Novice/Intermediate/Expert/Master) and writes the row.

Run any script with:
```
python app.py
# or
python description.py
python difficulty.py
python length.py
python skilllevel.py
```

## Environment Variables
Defined/used across the scripts (see `.env.example` for defaults):
- `OPENAI_API_KEY` (required): Your API key.
- `OPENAI_MODEL`: Model name (default in code: `gpt-5`).
- `INPUT_CSV`, `OUTPUT_CSV`: Input and output file paths.
- `LOG_LEVEL`: `DEBUG|INFO|WARNING|ERROR` (default `INFO`).
- `NO_COLOR`: `1` disables colored log output.
- `OPENAI_REQUEST_TIMEOUT`: Request timeout in seconds (default `60`).
- `OPENAI_MAX_RETRIES`: Internal retries in the OpenAI client (default `1`).
- `MAX_RETRIES`: Outer retry loop for our requests (default `6`).
- `RATE_LIMIT_RPM`: Requests per minute target (default `1`).
- `BATCH_SIZE`: Rows to process per batch before cooldown (default `1`).
- `BATCH_PAUSE_SECONDS`: Cooldown between batches (default `15`).
- `ENABLE_WEB_SEARCH`: Enable `web_search_preview` tool when available (`1|0`). If you don’t have access, set `0`.
- `DISABLE_RESPONSES_FORMAT`: Set `1` to avoid JSON‑schema response_format when using Responses API.
- `FORCE_CHAT_COMPLETIONS`: Set `1` to force Chat Completions path.
- `FORCE_RESPONSES`: Set `1` to force the Responses API path.
- `SKIP_OPENAI_HEALTH_CHECK`: Set `1` to skip a startup model availability check.
- `CLEAR_OUTPUT_FILE`: Set `1` to clear `output.csv` and write only the header at start.

## Behavior Notes
- Resume safety: When not clearing the output file, the scripts skip links already present in `output.csv` (link‑based resume).
- Rate limits: A per‑request delay is computed from `RATE_LIMIT_RPM`, plus batch‑level cooldowns after `BATCH_SIZE` rows to reduce burst risk.
- Health check: On startup, scripts can verify `OPENAI_API_KEY` and model availability. Use `SKIP_OPENAI_HEALTH_CHECK=1` to bypass (e.g., when model retrieval is restricted but requests will still succeed).
- Responses vs. Chat: Scripts prefer the Responses API with JSON schema; they can fall back to Chat Completions or disable schema formatting if your environment doesn’t support it.

## Troubleshooting
- `OPENAI_API_KEY is not set`: Ensure it’s present in `.env` or your environment.
- Model/Responses errors: Try `DISABLE_RESPONSES_FORMAT=1` or `FORCE_CHAT_COMPLETIONS=1`.
- Tooling access: If you lack `web_search_preview`, set `ENABLE_WEB_SEARCH=0`.

