#!/usr/bin/env python3
import csv, os, time, json, pathlib, sys, logging, re
from typing import Dict, Any, Set
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError, RateLimitError

# Load .env if present
load_dotenv(override=False)

# ====== CONFIG ======
INPUT_CSV  = os.getenv("INPUT_CSV", "input.csv")
OUTPUT_CSV = os.getenv("OUTPUT_CSV", os.path.join("data", "courses.csv"))
OUTPUT_JSON = os.getenv("OUTPUT_JSON", os.path.join("data", "courses.json"))
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
    path = pathlib.Path(OUTPUT_CSV)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=HEADERS).writeheader()
    ensure_json_file()


def ensure_json_file():
    path = pathlib.Path(OUTPUT_JSON)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", encoding="utf-8") as f:
            json.dump([], f)


def clear_output_file():
    try:
        csv_path = pathlib.Path(OUTPUT_CSV)
        if csv_path.exists():
            csv_path.unlink()
            logging.info(f"Removed existing {OUTPUT_CSV}.")
        json_path = pathlib.Path(OUTPUT_JSON)
        if json_path.exists():
            json_path.unlink()
            logging.info(f"Removed existing {OUTPUT_JSON}.")
    except Exception as e:
        logging.warning(f"Could not remove output artifacts: {e}. Will overwrite header.")
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


# ====== PROMPTS ======
SYSTEM_CLASSIFY = """
You judge whether a course summary is a valid, informative description of the course content.
Return ONLY TRUE or FALSE. TRUE means the summary is valid. FALSE means it is missing, a placeholder (e.g., Unknown/N/A), says a description couldn't be found, or is otherwise not a meaningful summary.
"""

USER_CLASSIFY_TMPL = """
Consider this course record and its current Summary. Decide if Summary is a valid course description.

Course record JSON:
{row_json}

Return ONLY: TRUE or FALSE (uppercase, no punctuation).
"""

SYSTEM_SUMMARY = """
You are a precise researcher. Produce a concise, neutral course summary ≤256 characters.
- Use the course Link and public sources; sum up key topics and outcomes.
- Avoid fluff, marketing, and repetition. No quotes or citations.
Return ONLY the JSON requested by the user.
"""

USER_SUMMARY_TMPL = """
Using the record below, research the linked course and write a concise, neutral Summary ≤256 characters describing the course’s content and outcomes.

Course record JSON:
{row_json}

Return ONLY a JSON object with this shape:
{{
  "Summary": "<TEXT UP TO 256 CHARS>"
}}
"""


def call_model_classify(full_row: Dict[str, Any]) -> bool:
    prompt = USER_CLASSIFY_TMPL.format(row_json=json.dumps(full_row, ensure_ascii=False))
    enable_web = os.getenv("ENABLE_WEB_SEARCH", "1").lower() in {"1", "true", "yes"}

    def do_request(use_web: bool):
        kwargs = {
            "model": MODEL,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_CLASSIFY}]},
                {"role": "user",   "content": [{"type": "input_text", "text": prompt}]},
            ],
            "temperature": 0.0,
        }
        if use_web:
            kwargs["tools"] = [{"type": "web_search_preview"}]
        try:
            resp = get_client().responses.create(timeout=REQUEST_TIMEOUT, **kwargs)
            return resp, "responses+minimal", bool(use_web)
        except OpenAIError:
            cc = get_client().chat.completions.create(
                timeout=REQUEST_TIMEOUT,
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_CLASSIFY},
                    {"role": "user",   "content": prompt},
                ],
            )
            return cc, "chat+plain", False

    delay = 2
    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            resp, path, used_web = do_request(enable_web)
            dt = time.time() - t0
            usage = extract_usage(resp)
            logging.info(f"⏱️ {dt:.2f}s | 🧠 tokens(in={usage['in'] or '?'} out={usage['out'] or '?'} total={usage['total'] or '?'}) | 🧩 path={path} | 🔎 web_search={'on' if used_web else 'off'}")

            # Parse boolean from text or JSON
            text = getattr(resp, "output_text", None)
            if not text:
                # try chat
                try:
                    choices = getattr(resp, "choices", None)
                    if choices:
                        msg = getattr(choices[0], "message", None)
                        text = getattr(msg, "content", None) or (isinstance(msg, dict) and msg.get("content"))
                except Exception:
                    pass
            s = (text or "").strip().lower()
            if s in {"true", "false"}:
                return s == "true"
            # try JSON object with a boolean
            try:
                data = parse_response_to_json(resp)
                for k, v in (data or {}).items():
                    if isinstance(v, bool):
                        return v
                    if isinstance(v, str) and v.strip().lower() in {"true", "false"}:
                        return v.strip().lower() == "true"
            except Exception:
                pass
            # default: consider not valid to be safe
            return False
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
            logging.error(f"Non-retryable OpenAI error on classify: {e}")
            return False
        except Exception as e:
            logging.exception(f"Unexpected error on classify: {e}")
            return False
    return False


def call_model_summary(full_row: Dict[str, Any]) -> str:
    prompt = USER_SUMMARY_TMPL.format(row_json=json.dumps(full_row, ensure_ascii=False))
    enable_web = os.getenv("ENABLE_WEB_SEARCH", "1").lower() in {"1", "true", "yes"}

    def do_request(use_web: bool):
        # Prefer Responses with schema, but handle fallbacks
        kwargs = {
            "model": MODEL,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_SUMMARY}]},
                {"role": "user",   "content": [{"type": "input_text", "text": prompt}]},
            ],
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "CourseSummaryOnly",
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["Summary"],
                        "properties": {
                            "Summary": {"type": "string", "maxLength": 256}
                        }
                    },
                    "strict": True,
                },
            },
        }
        if use_web:
            kwargs["tools"] = [{"type": "web_search_preview"}]
        try:
            resp = get_client().responses.create(timeout=REQUEST_TIMEOUT, **kwargs)
            return resp, "responses+schema", bool(use_web)
        except (TypeError, OpenAIError):
            # Minimal Responses
            kwargs_min = {
                "model": MODEL,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_SUMMARY}]},
                    {"role": "user",   "content": [{"type": "input_text", "text": prompt + "\n\nReturn ONLY a JSON object with key 'Summary'."}]},
                ],
            }
            if use_web:
                kwargs_min["tools"] = [{"type": "web_search_preview"}]
            try:
                resp2 = get_client().responses.create(timeout=REQUEST_TIMEOUT, **kwargs_min)
                return resp2, "responses+minimal", bool(use_web)
            except OpenAIError:
                # Chat fallback
                cc = get_client().chat.completions.create(
                    timeout=REQUEST_TIMEOUT,
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_SUMMARY},
                        {"role": "user",   "content": prompt + "\n\nReturn ONLY a JSON object with key 'Summary'."},
                    ],
                )
                return cc, "chat+plain", False

    delay = 2
    for attempt in range(MAX_RETRIES):
        try:
            t0 = time.time()
            resp, path, used_web = do_request(enable_web)
            data = parse_response_to_json(resp)
            dt = time.time() - t0
            usage = extract_usage(resp)
            logging.info(f"⏱️ {dt:.2f}s | 🧠 tokens(in={usage['in'] or '?'} out={usage['out'] or '?'} total={usage['total'] or '?'}) | 🧩 path={path} | 🔎 web_search={'on' if used_web else 'off'}")

            summary_val = str(data.get("Summary") or "").strip()
            if len(summary_val) > 256:
                summary_val = summary_val[:256].rstrip()
            if not summary_val:
                logging.warning("Summary returned empty; using 'Unknown'.")
                summary_val = "Unknown"
            return summary_val
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
            logging.error(f"Non-retryable OpenAI error while fetching Summary: {e}")
            return "Unknown"
        except Exception as e:
            logging.exception(f"Unexpected error while fetching Summary: {e}")
            return "Unknown"
    return "Unknown"


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
    out["Length"] = out.get("Length") or "0 Hours"
    out["Evidence of Completion"] = out.get("Evidence of Completion") or "Unknown"
    return out


def append_row(row: Dict[str, Any]):
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=HEADERS).writerow(row)
        f.flush()
    append_json_row(row)


def append_json_row(row: Dict[str, Any]):
    ensure_json_file()
    path = pathlib.Path(OUTPUT_JSON)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                data = []
    except (json.JSONDecodeError, FileNotFoundError):
        data = []

    data.append(row)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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

            # 1) Determine if Summary is valid
            is_valid = call_model_classify(row)
            last_call_ts = time.time()

            # 2) If valid, write as-is; else generate a new one
            if is_valid:
                out = canonicalize_full_row(row)
                append_row(out)
                logging.info(f"Summary valid ✅: {provider} | {link}")
            else:
                new_summary = call_model_summary(row)
                row["Summary"] = new_summary
                out = canonicalize_full_row(row)
                append_row(out)
                logging.info(f"Summary updated ✏️: {provider} | {link}")
            processed += 1

            if processed % BATCH_SIZE == 0:
                batch_index += 1
                logging.info(f"Completed batch #{batch_index}: {processed}/{to_process_total} processed. Cooling down {BATCH_PAUSE_SECONDS}s…")
                time.sleep(BATCH_PAUSE_SECONDS)

    logging.info(f"Done. Processed: {processed} | Skipped: {skipped}")


if __name__ == "__main__":
    main()
