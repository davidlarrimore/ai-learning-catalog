#!/usr/bin/env python3
import csv, os, time, json, pathlib, sys, logging, re
from typing import Dict, Any, Set
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError, RateLimitError

# Load .env if present
load_dotenv(override=False)

# ====== CONFIG ======
INPUT_CSV  = os.getenv("INPUT_CSV", "input.csv")
OUTPUT_CSV = os.getenv("OUTPUT_CSV", "output.csv")
MODEL      = os.getenv("OPENAI_MODEL", "gpt-5")

RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "1"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))
BATCH_PAUSE_SECONDS = int(os.getenv("BATCH_PAUSE_SECONDS", "15"))
REQUEST_TIMEOUT = float(os.getenv("OPENAI_REQUEST_TIMEOUT", "60"))
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "1"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "6"))

PER_REQUEST_DELAY = 60.0 / max(RATE_LIMIT_RPM, 1)

# Output headers (must match main app)
HEADERS = [
    "Provider","Link","Course Name","Summary","Track","Platform",
    "Hands On","Skill Level","Difficulty","Length","Evidence of Completion"
]

# ====== LOGGING ======
class EmojiColorFormatter(logging.Formatter):
    RESET = "\033[0m"
    COLORS = {
        logging.DEBUG: "\033[36m",
        logging.INFO: "\033[32m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[41m",
    }
    EMOJI = {
        logging.DEBUG: "🔍",
        logging.INFO: "✅",
        logging.WARNING: "⚠️",
        logging.ERROR: "❌",
        logging.CRITICAL: "🛑",
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, "")
        emoji = self.EMOJI.get(record.levelno, "")
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created))
        if os.getenv("NO_COLOR", "0").lower() in {"1", "true", "yes"}:
            return f"{ts} {record.levelname} {emoji} {record.getMessage()}"
        return f"{color}{ts} {record.levelname} {emoji} {record.getMessage()}{self.RESET}"


def setup_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    if root.handlers:
        for h in root.handlers:
            h.setLevel(getattr(logging, level, logging.INFO))
            h.setFormatter(EmojiColorFormatter())
        root.setLevel(getattr(logging, level, logging.INFO))
    else:
        handler = logging.StreamHandler()
        handler.setLevel(getattr(logging, level, logging.INFO))
        handler.setFormatter(EmojiColorFormatter())
        root.addHandler(handler)
        root.setLevel(getattr(logging, level, logging.INFO))


# ====== OPENAI CLIENT + HELPERS ======
_client = None
def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(timeout=REQUEST_TIMEOUT, max_retries=OPENAI_MAX_RETRIES)
    return _client


def check_openai_health(model: str, attempts: int = 2) -> bool:
    if not os.getenv("OPENAI_API_KEY"):
        logging.error("Health check failed: OPENAI_API_KEY not set.")
        return False
    delay = 2
    for i in range(attempts):
        try:
            logging.info(f"OpenAI health: checking model '{model}' (attempt {i+1}/{attempts})…")
            _ = get_client().models.retrieve(model)
            logging.info(f"OpenAI health: model '{model}' is available.")
            return True
        except RateLimitError as e:
            logging.warning(f"OpenAI health: rate limited during check: {e}. Retrying in {delay}s…")
            time.sleep(delay)
            delay = min(delay * 2, 8)
        except OpenAIError as e:
            status = getattr(e, "status_code", "NA")
            logging.error(f"OpenAI health: API error while retrieving model '{model}' (status {status}): {e}")
            return False
        except Exception as e:
            logging.exception(f"OpenAI health: unexpected error: {e}")
            return False
    logging.error("OpenAI health: repeated rate limits; health indeterminate.")
    return False


def ensure_output_header():
    if not pathlib.Path(OUTPUT_CSV).exists():
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=HEADERS).writeheader()


def clear_output_file():
    try:
        p = pathlib.Path(OUTPUT_CSV)
        if p.exists():
            p.unlink()
            logging.info(f"Removed existing {OUTPUT_CSV}.")
    except Exception as e:
        logging.warning(f"Could not remove {OUTPUT_CSV}: {e}. Will overwrite header.")
    ensure_output_header()
    logging.info(f"Cleared {OUTPUT_CSV} per CLEAR_OUTPUT_FILE=1.")


def load_processed_links() -> Set[str]:
    links: Set[str] = set()
    if pathlib.Path(OUTPUT_CSV).exists():
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                link = (r.get("Link") or "").strip()
                if link:
                    links.add(link)
    return links


def extract_usage(resp) -> Dict[str, Any]:
    usage_info = {"in": None, "out": None, "total": None}
    try:
        usage = getattr(resp, "usage", None) or (isinstance(resp, dict) and resp.get("usage"))
        if not usage:
            return usage_info
        for key_from, key_to in [("input_tokens", "in"), ("output_tokens", "out"), ("total_tokens", "total")]:
            val = getattr(usage, key_from, None) or (isinstance(usage, dict) and usage.get(key_from))
            if val is not None:
                usage_info[key_to] = int(val)
        if usage_info["in"] is None:
            v = getattr(usage, "prompt_tokens", None) or (isinstance(usage, dict) and usage.get("prompt_tokens"))
            if v is not None:
                usage_info["in"] = int(v)
        if usage_info["out"] is None:
            v = getattr(usage, "completion_tokens", None) or (isinstance(usage, dict) and usage.get("completion_tokens"))
            if v is not None:
                usage_info["out"] = int(v)
        if usage_info["total"] is None:
            v = getattr(usage, "total_tokens", None) or (isinstance(usage, dict) and usage.get("total_tokens"))
            if v is not None:
                usage_info["total"] = int(v)
    except Exception:
        pass
    return usage_info


def parse_json_loose(s: str) -> Dict[str, Any]:
    s = (s or "").strip()
    if not s:
        raise ValueError("empty string")
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    try:
        return json.loads(s)
    except Exception:
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(s[start:end+1])
        raise


def parse_response_to_json(resp) -> Dict[str, Any]:
    parsed = getattr(resp, "output_parsed", None)
    if parsed:
        return parsed
    text = getattr(resp, "output_text", None)
    if text:
        return parse_json_loose(text)
    # chat completions
    try:
        choices = getattr(resp, "choices", None)
        if choices:
            msg = getattr(choices[0], "message", None)
            content = None
            if msg is not None:
                content = getattr(msg, "content", None) or (isinstance(msg, dict) and msg.get("content"))
            if content:
                return parse_json_loose(content)
    except Exception:
        pass
    # responses streaming
    try:
        chunks = []
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                if getattr(c, "type", "") == "output_text" and getattr(c, "text", None):
                    chunks.append(c.text)
        if chunks:
            return parse_json_loose("".join(chunks))
    except Exception:
        pass
    raise RuntimeError("Could not parse model response into JSON.")


# ====== LENGTH PROMPT ======
SYSTEM_INSTRUCTIONS = """
You are a precise researcher tasked with estimating the total time to complete a course.

Rules:
- Use the provided course Link and perform web research. If login-gated, rely on public pages, catalogs, or cached copies.
- Sum durations of modules/videos/lessons if listed; otherwise infer conservatively from syllabus, number of modules, or typical lengths.
- Return Length as a rounded integer hours string like "12 Hours". If truly unknown, return "0 Hours".
- Do NOT include any other fields or commentary; follow the output instruction strictly.
"""

USER_TEMPLATE = """
Given this course record, research the linked course and estimate total time to complete. If modules/videos are listed, sum them. Otherwise infer conservatively.

Course record JSON:
{row_json}

Return ONLY a JSON object with this shape:
{{
  "Length": "<INTEGER> Hours"
}}
"""


def call_model_for_length(full_row: Dict[str, Any]) -> str:
    prompt = USER_TEMPLATE.format(row_json=json.dumps(full_row, ensure_ascii=False))

    force_chat = os.getenv("FORCE_CHAT_COMPLETIONS", "0").lower() in {"1", "true", "yes"}
    disable_responses_format = os.getenv("DISABLE_RESPONSES_FORMAT", "1").lower() in {"1", "true", "yes"}
    enable_web = os.getenv("ENABLE_WEB_SEARCH", "1").lower() in {"1", "true", "yes"}

    def do_request(use_web: bool):
        kwargs_new = {
            "model": MODEL,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_INSTRUCTIONS}]},
                {"role": "user",   "content": [{"type": "input_text", "text": prompt}]},
            ],
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "CourseLengthOnly",
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["Length"],
                        "properties": {
                            "Length": {"type": "string", "pattern": r"^\\d+\\s+Hours?$"}
                        }
                    },
                    "strict": True,
                },
            },
        }
        if use_web:
            kwargs_new["tools"] = [{"type": "web_search_preview"}]

        try:
            if disable_responses_format:
                raise TypeError("response_format disabled via env")
            logging.debug("Attempting Responses.create (schema)…")
            resp = get_client().responses.create(timeout=REQUEST_TIMEOUT, **kwargs_new)
            return resp, "responses+schema", bool(use_web)
        except (TypeError, OpenAIError):
            # Minimal responses
            kwargs_min = {
                "model": MODEL,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_INSTRUCTIONS}]},
                    {"role": "user",   "content": [{"type": "input_text", "text": prompt + "\n\nReturn ONLY a JSON object with key 'Length'."}]},
                ],
            }
            if use_web:
                kwargs_min["tools"] = [{"type": "web_search_preview"}]
            logging.debug("Attempting Responses.create (minimal)…")
            try:
                resp2 = get_client().responses.create(timeout=REQUEST_TIMEOUT, **kwargs_min)
                return resp2, "responses+minimal", bool(use_web)
            except OpenAIError:
                # Chat fallback
                logging.debug("Attempting chat.completions (plain)…")
                cc = get_client().chat.completions.create(
                    timeout=REQUEST_TIMEOUT,
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                        {"role": "user", "content": prompt + "\n\nReturn ONLY a JSON object with key 'Length'."},
                    ],
                )
                return cc, "chat+plain", False

    delay = 2
    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            if force_chat:
                resp, path, used_web = get_client().chat.completions.create(
                    timeout=REQUEST_TIMEOUT,
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                        {"role": "user", "content": prompt + "\n\nReturn ONLY a JSON object with key 'Length'."},
                    ],
                ), "chat+plain", False
            else:
                resp, path, used_web = do_request(enable_web)
            data = parse_response_to_json(resp)
            dt = time.time() - t0
            usage = extract_usage(resp)
            logging.info(f"⏱️ {dt:.2f}s | 🧠 tokens(in={usage['in'] or '?'} out={usage['out'] or '?'} total={usage['total'] or '?'}) | 🧩 path={path} | 🔎 web_search={'on' if used_web else 'off'}")

            length_val = str(data.get("Length") or "").strip()
            # Validate format (allow singular/plural); then coerce 0 to 1 Hour
            if not length_val or not re.match(r"^\d+\s+Hours?$", length_val):
                logging.warning(f"Length not in expected format; got '{length_val}'. Using '1 Hour'.")
                length_val = "1 Hour"
            elif re.match(r"^0\s+Hours?$", length_val):
                logging.warning("Length returned as 0; defaulting to '1 Hour'.")
                length_val = "1 Hour"
            return length_val
        except RateLimitError:
            if attempt == MAX_RETRIES - 1:
                raise
            logging.warning(f"Rate limit; backing off {delay}s (attempt {attempt+1}/{MAX_RETRIES}).")
            time.sleep(delay)
            delay = min(delay * 2, 30)
        except OpenAIError as e:
            if attempt < MAX_RETRIES - 1 and getattr(e, "status_code", 500) >= 500:
                logging.warning(f"OpenAIError {getattr(e, 'status_code', 'NA')}; retrying in {delay}s (attempt {attempt+1}/{MAX_RETRIES}).")
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            logging.error(f"Non-retryable OpenAI error while fetching Length: {e}")
            return "1 Hour"
        except Exception as e:
            logging.exception(f"Unexpected error while fetching Length: {e}")
            return "1 Hour"
    return "1 Hour"


def canonicalize_full_row(row: Dict[str, Any]) -> Dict[str, Any]:
    # Copy and normalize for CSV output
    out = {h: "" for h in HEADERS}
    # Map likely keys (robust normalization)
    def nkey(k: str) -> str:
        s = str(k).strip().lower()
        s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
        return s
    keymap = {
        "provider": "Provider",
        "link": "Link",
        "course_name": "Course Name",
        "course_title": "Course Name",
        "title": "Course Name",
        "summary": "Summary",
        "track": "Track",
        "tracks": "Track",
        "platform": "Platform",
        "hands_on": "Hands On",
        "handson": "Hands On",
        "skill_level": "Skill Level",
        "skilllevel": "Skill Level",
        "difficulty": "Difficulty",
        "length": "Length",
        "evidence_of_completion": "Evidence of Completion",
        "evidence": "Evidence of Completion",
    }
    for k, v in row.items():
        tgt = keymap.get(nkey(k))
        if not tgt:
            continue
        if tgt == "Track" and isinstance(v, list):
            out[tgt] = "; ".join([str(x).strip() for x in v])
        elif isinstance(v, str):
            out[tgt] = " ".join(v.split())
        else:
            out[tgt] = str(v)
    # Fill defaults for missing
    out.setdefault("Provider", out.get("Provider", ""))
    out.setdefault("Link", out.get("Link", ""))
    out["Course Name"] = out.get("Course Name") or "Unknown"
    out["Summary"] = out.get("Summary") or "Unknown"
    out["Track"] = out.get("Track") or ""
    out["Platform"] = out.get("Platform") or ""
    out["Hands On"] = out.get("Hands On") or "Unknown"
    out["Skill Level"] = out.get("Skill Level") or "Unknown"
    out["Difficulty"] = out.get("Difficulty") or "Unknown"
    out["Length"] = out.get("Length") or "1 Hour"
    out["Evidence of Completion"] = out.get("Evidence of Completion") or "Unknown"
    return out


def append_row(row: Dict[str, Any]):
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=HEADERS).writerow(row)
        f.flush()


def main():
    setup_logging()
    if not os.getenv("OPENAI_API_KEY"):
        logging.error("OPENAI_API_KEY is not set in your environment.")
        sys.exit(1)

    skip_health = os.getenv("SKIP_OPENAI_HEALTH_CHECK", "0").lower() in {"1","true","yes"}
    if not skip_health and not check_openai_health(MODEL):
        logging.error("Aborting due to OpenAI API health check failure. Set SKIP_OPENAI_HEALTH_CHECK=1 to bypass.")
        sys.exit(2)

    if os.getenv("CLEAR_OUTPUT_FILE", "0").lower() in {"1","true","yes"}:
        clear_output_file()
    else:
        ensure_output_header()

    already_links = load_processed_links()
    logging.info(f"Resume mode: {len(already_links)} links already in {OUTPUT_CSV}.")
    logging.info(f"Rate limiting: ~{RATE_LIMIT_RPM} rpm (per-request {PER_REQUEST_DELAY:.2f}s); batch size {BATCH_SIZE}, cooldown {BATCH_PAUSE_SECONDS}s.")

    with open(INPUT_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"Provider", "Link"}
        fieldnames = [fn.strip() for fn in (reader.fieldnames or [])]
        if not required.issubset(set(fieldnames)):
            logging.error(f"Input header detected: {fieldnames}")
            raise ValueError(f"Input must include columns: {sorted(required)}")

        rows = [r for r in reader if not all(((v or "").strip() == "") for v in r.values())]
        to_process_total = sum(1 for r in rows if (r.get("Link") or "").strip() not in already_links)
        logging.info(f"Plan: process {to_process_total} of {len(rows)} input rows (skipping {len(rows) - to_process_total} existing).")

        processed = 0
        skipped = 0
        batch_index = 0
        last_call_ts = 0.0

        for row in rows:
            provider = (row.get("Provider") or "").strip()
            link = (row.get("Link") or "").strip()
            if not provider or not link:
                # keep parity; but we cannot research
                out = canonicalize_full_row(row)
                append_row(out)
                logging.info(f"Placeholder appended (missing fields): {provider} | {link}")
                processed += 1
                continue

            if link in already_links:
                skipped += 1
                logging.info(f"🔁 Skipping existing link, already in {OUTPUT_CSV}: {link}")
                continue

            # throttle per-request
            now = time.time()
            wait = max(0.0, (last_call_ts + PER_REQUEST_DELAY) - now)
            if wait > 0:
                time.sleep(wait)

            # Call model to get Length
            length_val = call_model_for_length(row)
            last_call_ts = time.time()

            # Update row & write
            row["Length"] = length_val
            out = canonicalize_full_row(row)
            append_row(out)
            processed += 1
            logging.info(f"Processed Length: {provider} | {link} → {length_val}")

            if processed % BATCH_SIZE == 0:
                batch_index += 1
                logging.info(f"Completed batch #{batch_index}: {processed}/{to_process_total} processed. Cooling down {BATCH_PAUSE_SECONDS}s…")
                time.sleep(BATCH_PAUSE_SECONDS)

    logging.info(f"Done. Processed: {processed} | Skipped: {skipped}")


if __name__ == "__main__":
    main()
