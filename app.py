#!/usr/bin/env python3
import csv, os, time, json, pathlib, sys, logging
import re
from dotenv import load_dotenv
from typing import Dict, Any, Set, Tuple
from urllib.parse import urlparse

from openai import OpenAI, OpenAIError, RateLimitError  # <-- fixed import

# Load environment from a local .env file if present (non-destructive)
load_dotenv(override=False)

# ====== CONFIG ======
INPUT_CSV  = "input.csv"     # your input file
OUTPUT_CSV = os.getenv("OUTPUT_CSV", os.path.join("data", "courses.csv"))    # your output file
OUTPUT_JSON = os.getenv("OUTPUT_JSON", os.path.join("data", "courses.json"))
# Preserve original default; allow env override without changing behavior
MODEL      = os.getenv("OPENAI_MODEL", "gpt-5")  # Responses API model
MAX_RETRIES = 6
REQUEST_TIMEOUT = float(os.getenv("OPENAI_REQUEST_TIMEOUT", "60"))
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "1"))

# Rate limiting & batching (env-overridable)
# - RATE_LIMIT_RPM: max requests per minute (approx). A per-request sleep is computed as 60/RPM.
# - BATCH_SIZE: how many rows to process before taking a longer pause.
# - BATCH_PAUSE_SECONDS: how long to sleep after each batch to stay under burst limits.
RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "1"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))
BATCH_PAUSE_SECONDS = int(os.getenv("BATCH_PAUSE_SECONDS", "15"))

PER_REQUEST_DELAY = 60.0 / max(RATE_LIMIT_RPM, 1)

# CSV output headers (single source of truth)
HEADERS = [
    "Provider","Link","Course Name","Summary","Track","Platform",
    "Hands On","Skill Level","Difficulty","Length","Evidence of Completion"
]

# Tracks whitelist (cap at 3)
TRACKS = [
    "AI Literacy", "Prompt Engineering", "Python Development", "RAG",
    "Responsible AI", "Machine Learning", "Data Science", "MLOps", "Technical Skills"
]

# JSON Schema (schema-only; name moves to text.format.name)
COURSE_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "Provider": {"type": "string"},
        "Link": {"type": "string"},
        "Course Name": {"type": "string"},
        "Summary": {"type": "string", "maxLength": 256},
        "Track": {
            "type": "array",
            "items": {"type": "string", "enum": [
                "AI Literacy", "Prompt Engineering", "Python Development", "RAG",
                "Responsible AI", "Machine Learning", "Data Science", "MLOps", "Technical Skills"
            ]},
            "minItems": 0, "maxItems": 3
        },
        "Platform": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 0,
            "maxItems": 10,
            "description": "List of specific tools, software, platforms, or libraries taught (e.g., LangChain, AWS, PowerApps, Python, UiPath)."
        },
        "Hands On": {"type": "string", "enum": ["Yes", "No", "Unknown"]},
        "Skill Level": {"type": "string", "enum": ["Novice", "Intermediate", "Expert", "Master", "Unknown"]},
        "Difficulty": {"type": "string", "enum": ["Low", "Medium", "High", "Unknown"]},
        "Length": {
            "type": "string",
            "pattern": r"^\d+\s+Hours$",
            "description": "Rounded integer hours, e.g. '12 Hours'. If unknown, use '0 Hours'."
        },
        "Evidence of Completion": {"type": "string"}
    },
    "required": [
        "Provider","Link","Course Name","Summary","Track","Platform","Hands On",
        "Skill Level","Difficulty","Length","Evidence of Completion"
    ]
}

SYSTEM_INSTRUCTIONS = f"""
You are a meticulous researcher filling metadata on AI training courses.

Rules:
- Use the provided Link first. If it requires login, rely on public pages, cached copies, catalogs, or news posts about the course.
- Extract real details where possible; otherwise return 'Unknown' or '0 Hours' per schema rules.
- Summary must be ≤256 characters.
- Track: choose the best 1–3 from this fixed list: {', '.join(TRACKS)} (never invent new labels).
- Platform: return a list of the specific Tools, Software, Platforms, or Libraries that will be learned (e.g., LangChain, AWS, PowerApps, Python, UiPath). If none are explicit, return an empty list; do not put the hosting site name here.
- Length: integer hours rounded from durations; if only weeks or videos given, estimate hours conservatively and round.
- Hands On: 'Yes' if labs, projects, notebooks, exercises, or quizzes are explicitly included; 'No' if explicitly lecture-only; else 'Unknown'.
- Difficulty: subjective (Low/Medium/High) based on length, labs/challenges/exams; if unclear, 'Unknown'.
- Skill Level: Novice / Intermediate / Expert / Master / Unknown (choose the closest).
- Evidence of Completion: prefer official verifiables (badges, transcripts, certs). If audit-only, suggest:
  '100% progress screenshot + 150–200 word reflection' and optionally a small project artifact (GitHub/HF/PartyRock).
- Never leave 'Evidence of Completion' empty; if no official proof is available, use the suggested fallback text above.
- Output must strictly follow the JSON schema (no extra keys).
"""

USER_TEMPLATE = """
Fill the metadata for this course.

Provider: {provider}
Link: {link}

Return ONLY the JSON object as per schema.
"""

_client = None
def get_client() -> OpenAI:
    global _client
    if _client is None:
        # expects OPENAI_API_KEY in env
        _client = OpenAI(timeout=REQUEST_TIMEOUT, max_retries=OPENAI_MAX_RETRIES)
        
    return _client


def setup_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    # Custom formatter with colors + emojis for readability
    class EmojiColorFormatter(logging.Formatter):
        RESET = "\033[0m"
        COLORS = {
            logging.DEBUG: "\033[36m",    # cyan
            logging.INFO: "\033[32m",     # green
            logging.WARNING: "\033[33m",  # yellow
            logging.ERROR: "\033[31m",    # red
            logging.CRITICAL: "\033[41m", # red background
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
            msg = super().format(record)
            if os.getenv("NO_COLOR", "0").lower() in {"1", "true", "yes"}:
                return f"{ts} {record.levelname} {emoji} {record.getMessage()}"
            return f"{color}{ts} {record.levelname} {emoji} {record.getMessage()}{self.RESET}"

    # Avoid duplicate handlers on repeated initialization
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


def check_openai_health(model: str, attempts: int = 2) -> bool:
    """Lightweight health check: verifies API key and model availability.

    Returns True if the model can be retrieved; logs details on failure.
    """
    if not os.getenv("OPENAI_API_KEY"):
        logging.error("Health check failed: OPENAI_API_KEY not set.")
        return False

    delay = 2
    for i in range(attempts):
        try:
            logging.info(f"OpenAI health: checking model '{model}' (attempt {i+1}/{attempts})…")
            # Model existence/availability check
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
            writer = csv.DictWriter(f, fieldnames=HEADERS)
            writer.writeheader()
    ensure_json_file()


def ensure_json_file():
    path = pathlib.Path(OUTPUT_JSON)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with open(path, "w", encoding="utf-8") as f:
            json.dump([], f)


def clear_output_file():
    """Remove existing output.csv (if any) and recreate with header only."""
    try:
        path = pathlib.Path(OUTPUT_CSV)
        if path.exists():
            path.unlink()
            logging.info(f"Removed existing {OUTPUT_CSV}.")
        json_path = pathlib.Path(OUTPUT_JSON)
        if json_path.exists():
            json_path.unlink()
            logging.info(f"Removed existing {OUTPUT_JSON}.")
    except Exception as e:
        logging.warning(f"Could not remove output artifacts: {e}. Will overwrite header.")
    ensure_output_header()
    logging.info(f"Cleared {OUTPUT_CSV} per CLEAR_OUTPUT_FILE=1.")


def load_processed_pairs() -> Set[Tuple[str, str]]:
    """Read output.csv and return set of (Provider, Link) already done."""
    done: Set[Tuple[str, str]] = set()
    if pathlib.Path(OUTPUT_CSV).exists():
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                done.add((r.get("Provider","").strip(), r.get("Link","").strip()))
    return done


def load_processed_links() -> Set[str]:
    """Read output.csv and return set of Links already present (link-only resume)."""
    links: Set[str] = set()
    if pathlib.Path(OUTPUT_CSV).exists():
        with open(OUTPUT_CSV, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                link = (r.get("Link", "") or "").strip()
                if link:
                    links.add(link)
    return links


def append_row(row: Dict[str, Any]):
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=HEADERS).writerow(row)
        f.flush()  # ensure checkpointing per row
    append_json_row(row)


def append_json_row(row: Dict[str, Any]):
    path = pathlib.Path(OUTPUT_JSON)
    ensure_json_file()
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


def canonicalize_fields(d: Dict[str, Any], provider: str, link: str) -> Dict[str, Any]:
    target = {
        "Provider": provider or "",
        "Link": link or "",
        "Course Name": "Unknown",
        "Summary": "Unknown",
        "Track": "",
        "Platform": "Unknown",
        "Hands On": "Unknown",
        "Skill Level": "Unknown",
        "Difficulty": "Unknown",
        "Length": "0 Hours",
        "Evidence of Completion": "Unknown",
    }

    def norm_str(x: Any) -> str:
        return " ".join(str(x).split()) if isinstance(x, str) else str(x)

    keymap = {
        "provider": "Provider",
        "link": "Link",
        "course_name": "Course Name",
        "course title": "Course Name",
        "course_title": "Course Name",
        "coursetitle": "Course Name",
        "title": "Course Name",
        "name": "Course Name",
        "summary": "Summary",
        "track": "Track",
        "tracks": "Track",
        "platform": "Platform",
        "platform_name": "Platform",
        "hands_on": "Hands On",
        "hands-on": "Hands On",
        "hands": "Hands On",
        "handson": "Hands On",
        "skill_level": "Skill Level",
        "skilllevel": "Skill Level",
        "difficulty": "Difficulty",
        "length": "Length",
        "length_hours": "Length",
        "lengthhours": "Length",
        "evidence_of_completion": "Evidence of Completion",
        "evidence": "Evidence of Completion",
        "evidenceofcompletion": "Evidence of Completion",
        "proof_of_completion": "Evidence of Completion",
        "completion_proof": "Evidence of Completion",
        "completion_certificate": "Evidence of Completion",
        "certificate": "Evidence of Completion",
        "certification": "Evidence of Completion",
        "badge": "Evidence of Completion",
        "digital_badge": "Evidence of Completion",
        "digital badge": "Evidence of Completion",
        "shareable_certificate": "Evidence of Completion",
        "shareable certificate": "Evidence of Completion",
        "transcript": "Evidence of Completion",
        "credential": "Evidence of Completion",
    }

    def coerce_track(v: Any) -> str:
        vals: list[str] = []
        if isinstance(v, list):
            vals = [norm_str(x) for x in v]
        elif isinstance(v, str):
            parts = [p.strip() for p in v.replace(";", ",").split(",")]
            vals = [p for p in parts if p]
        allowed = {t.lower(): t for t in TRACKS}
        result = []
        for t in vals:
            tl = t.lower()
            if tl in allowed:
                result.append(allowed[tl])
        return "; ".join(result[:3])

    def coerce_length(v: Any) -> str:
        if isinstance(v, (int, float)):
            n = max(0, int(round(v)))
            return f"{n} Hours"
        s = norm_str(v)
        if s.isdigit():
            return f"{int(s)} Hours"
        num = ""
        for ch in s:
            if ch.isdigit():
                num += ch
            elif num:
                break
        if num:
            return f"{int(num)} Hours"
        return "0 Hours"

    def coerce_hands_on(v: Any) -> str:
        if isinstance(v, bool):
            return "Yes" if v else "No"
        s = norm_str(v).lower()
        if s in {"yes", "y", "true", "1"}:
            return "Yes"
        if s in {"no", "n", "false", "0"}:
            return "No"
        return "Unknown"

    def coerce_choice(v: Any, choices: set[str]) -> str:
        s = norm_str(v)
        # simple synonym mapping to reduce Unknowns
        syn = {
            # Skill level
            "beginner": "Novice",
            "novice": "Novice",
            "intermediate": "Intermediate",
            "advanced": "Expert",
            "expert": "Expert",
            "master": "Master",
            # Difficulty
            "easy": "Low",
            "medium": "Medium",
            "moderate": "Medium",
            "hard": "High",
            "high": "High",
            "low": "Low",
        }
        sl = s.lower()
        if sl in syn:
            mapped = syn[sl]
            if mapped in choices:
                return mapped
        for c in choices:
            if sl == c.lower():
                return c
        return "Unknown"

    def norm_key(key: Any) -> str:
        s = str(key).strip().lower()
        # Collapse any sequence of non-alphanumerics into a single underscore
        s = re.sub(r"[^a-z0-9]+", "_", s)
        return s.strip("_")

    lower_keys = {norm_key(k): k for k in d.keys()}
    for lk, orig_k in lower_keys.items():
        tgt = keymap.get(lk)
        if not tgt:
            continue
        val = d[orig_k]
        if tgt == "Track":
            target["Track"] = coerce_track(val)
        elif tgt == "Length":
            target["Length"] = coerce_length(val)
        elif tgt == "Hands On":
            target["Hands On"] = coerce_hands_on(val)
        elif tgt == "Skill Level":
            target["Skill Level"] = coerce_choice(val, {"Novice", "Intermediate", "Expert", "Master", "Unknown"})
        elif tgt == "Difficulty":
            target["Difficulty"] = coerce_choice(val, {"Low", "Medium", "High", "Unknown"})
        elif tgt == "Platform":
            # Accept list or delimited string; output is semicolon-separated string
            items: list[str] = []
            if isinstance(val, list):
                items = [norm_str(x) for x in val]
            else:
                s = norm_str(val)
                parts = [p.strip() for p in s.replace(";", ",").split(",")]
                items = [p for p in parts if p]
            # Deduplicate while preserving order
            seen = set()
            deduped: list[str] = []
            for it in items:
                low = it.lower()
                if low and low not in seen:
                    seen.add(low)
                    deduped.append(it)
            target["Platform"] = "; ".join(deduped)
        else:
            target[tgt] = norm_str(val)

    def coerce_evidence(v: Any) -> str:
        # Normalize various evidence descriptions to concise labels
        if isinstance(v, list):
            v = "; ".join([norm_str(x) for x in v if str(x).strip()])
        s = norm_str(v)
        sl = s.lower()
        if any(w in sl for w in ["digital badge", "badge"]):
            return "Digital Badge"
        if "certificate" in sl or "certification" in sl:
            return "Certificate"
        if "transcript" in sl:
            return "Transcript"
        if sl in {"yes", "true", "available"}:
            return "Certificate"
        if sl in {"no", "none", "n/a", "na", "not available"}:
            return "Unknown"
        return s

    # If model provided an evidence-like key but value is empty, retain default; else coerce
    ev = (target.get("Evidence of Completion", "") or "").strip()
    if ev and ev.lower() != "unknown":
        target["Evidence of Completion"] = coerce_evidence(ev)
    else:
        # As a last resort, use the recommended fallback pattern instead of leaving Unknown
        target["Evidence of Completion"] = (
            "100% progress screenshot + 150–200 word reflection; "
            "optionally include a small project artifact (GitHub/HF/PartyRock)."
        )


    for k in list(target.keys()):
        if isinstance(target[k], str):
            target[k] = " ".join(target[k].split())

    return target


def placeholder_row(provider: str, link: str) -> Dict[str, Any]:
    return {
        "Provider": provider, "Link": link, "Course Name": "Unknown",
        "Summary": "Unknown", "Track": "", "Platform": "Unknown",
        "Hands On": "Unknown", "Skill Level": "Unknown",
        "Difficulty": "Unknown", "Length": "0 Hours",
        "Evidence of Completion": "Unknown"
    }


def parse_response_to_json(resp) -> Dict[str, Any]:
    """
    Try multiple safe paths to extract the structured JSON from Responses API.
    Prefers structured outputs via resp.output_parsed; falls back to text parse.
    """
    # 1) Preferred: structured output
    parsed = getattr(resp, "output_parsed", None)
    if parsed:
        return parsed

    # Helper: tolerant JSON extraction from text
    def _parse_json_loose(s: str) -> Dict[str, Any]:
        s = s.strip()
        # Strip code fences
        if s.startswith("```"):
            # remove leading ```[json]? and trailing ```
            lines = s.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            s = "\n".join(lines).strip()
        # Direct parse
        try:
            return json.loads(s)
        except Exception:
            pass
        # Find first JSON object substring
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = s[start:end+1]
            try:
                return json.loads(candidate)
            except Exception:
                pass
        raise

    # 2) Fallback: output_text (SDK convenience)
    text = getattr(resp, "output_text", None)
    if text:
        return _parse_json_loose(text)

    # 3) Chat Completions shape
    try:
        choices = getattr(resp, "choices", None)
        if choices:
            first = choices[0]
            # new SDK: first.message.content; legacy may be dict-like
            msg = getattr(first, "message", None)
            content = None
            if msg is not None:
                content = getattr(msg, "content", None)
                if content is None and isinstance(msg, dict):
                    content = msg.get("content")
            if content:
                return _parse_json_loose(content)
    except Exception:
        pass

    # 4) Last resort: concatenate any text segments in resp.output (Responses streaming)
    try:
        chunks = []
        for item in getattr(resp, "output", []) or []:
            for c in getattr(item, "content", []) or []:
                if getattr(c, "type", "") == "output_text" and getattr(c, "text", None):
                    chunks.append(c.text)
        if chunks:
            return _parse_json_loose("".join(chunks))
    except Exception:
        pass

    # If all else fails, raise helpful error
    raise RuntimeError("Could not parse model response into JSON.")


def extract_usage(resp) -> Dict[str, Any]:
    """Best-effort extraction of token usage from either Responses or Chat APIs."""
    usage_info = {"in": None, "out": None, "total": None}
    try:
        usage = getattr(resp, "usage", None)
        if usage is None and isinstance(resp, dict):
            usage = resp.get("usage")
        if usage is None:
            return usage_info

        # Try Responses-style
        for key_from, key_to in [("input_tokens", "in"), ("output_tokens", "out"), ("total_tokens", "total")]:
            val = getattr(usage, key_from, None)
            if val is None and isinstance(usage, dict):
                val = usage.get(key_from)
            if val is not None:
                usage_info[key_to] = int(val)

        # Try Chat-style
        if usage_info["in"] is None:
            val = getattr(usage, "prompt_tokens", None) or (isinstance(usage, dict) and usage.get("prompt_tokens"))
            if val is not None:
                usage_info["in"] = int(val)
        if usage_info["out"] is None:
            val = getattr(usage, "completion_tokens", None) or (isinstance(usage, dict) and usage.get("completion_tokens"))
            if val is not None:
                usage_info["out"] = int(val)
        if usage_info["total"] is None:
            val = getattr(usage, "total_tokens", None) or (isinstance(usage, dict) and usage.get("total_tokens"))
            if val is not None:
                usage_info["total"] = int(val)
    except Exception:
        pass
    return usage_info


def call_model(provider: str, link: str) -> Dict[str, Any]:
    """Calls the Responses API with structured JSON output, optionally using web search."""
    prompt = USER_TEMPLATE.format(provider=provider, link=link)

    # Feature flags (env)
    force_chat = os.getenv("FORCE_CHAT_COMPLETIONS", "0").lower() in {"1", "true", "yes"}
    force_responses = os.getenv("FORCE_RESPONSES", "0").lower() in {"1", "true", "yes"}
    disable_responses_format = os.getenv("DISABLE_RESPONSES_FORMAT", "0").lower() in {"1", "true", "yes"}

    def do_request(use_web_search: bool):
        # Preferred (newer SDK): typed content parts + response_format
        kwargs_new: Dict[str, Any] = {
            "model": MODEL,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": SYSTEM_INSTRUCTIONS}],
                },
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                },
            ],
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "CourseRow",
                    "schema": COURSE_JSON_SCHEMA,
                    "strict": True,
                },
            },
        }
        if use_web_search:
            kwargs_new["tools"] = [{"type": "web_search_preview"}]

        try:
            if disable_responses_format:
                raise TypeError("response_format disabled via env")
            logging.debug("Attempting Responses.create with JSON schema…")
            resp = get_client().responses.create(timeout=REQUEST_TIMEOUT, **kwargs_new)
            return resp, "responses+schema", bool(use_web_search)
        except TypeError as te:
            # Try a minimal Responses call without response_format/temperature before abandoning Responses path
            logging.warning(f"Responses API signature mismatch: {te}. Trying minimal Responses call…")
            try:
                kwargs_min = {
                    "model": MODEL,
                    "input": [
                        {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_INSTRUCTIONS}]},
                        {"role": "user",   "content": [{"type": "input_text", "text": prompt}]},
                    ],
                }
                if use_web_search:
                    kwargs_min["tools"] = [{"type": "web_search_preview"}]
                logging.info("Attempting minimal Responses.create (no schema)…")
                resp_min = get_client().responses.create(timeout=REQUEST_TIMEOUT, **kwargs_min)
                logging.info("Minimal Responses call succeeded.")
                return resp_min, "responses+minimal", bool(use_web_search)
            except Exception as oe_min:
                status_m = getattr(oe_min, "status_code", None)
                logging.warning(f"Minimal Responses call failed (status {status_m}): {oe_min}. Falling back to chat.completions…")
        except OpenAIError as oe:
            status = getattr(oe, "status_code", None)
            msg = str(oe)
            logging.warning(f"Responses API error (status {status}): {msg}. Trying minimal Responses call…")
            try:
                kwargs_min = {
                    "model": MODEL,
                    "input": [
                        {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_INSTRUCTIONS}]},
                        {"role": "user",   "content": [{"type": "input_text", "text": prompt}]},
                    ],
                }
                if use_web_search:
                    kwargs_min["tools"] = [{"type": "web_search_preview"}]
                logging.info("Attempting minimal Responses.create (no schema)…")
                resp_min2 = get_client().responses.create(timeout=REQUEST_TIMEOUT, **kwargs_min)
                logging.info("Minimal Responses call succeeded.")
                return resp_min2, "responses+minimal", bool(use_web_search)
            except Exception as oe_min2:
                status_m2 = getattr(oe_min2, "status_code", None)
                logging.warning(f"Minimal Responses call failed (status {status_m2}): {oe_min2}. Trying chat.completions fallback…")

        # Chat Completions fallback with JSON Schema, handling temperature incompatibility
        def chat_call(include_schema: bool, include_temp: bool):
            kwargs_cc: Dict[str, Any] = {
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                    {"role": "user",   "content": prompt},
                ],
            }
            if include_schema:
                kwargs_cc["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "CourseRow",
                        "schema": COURSE_JSON_SCHEMA,
                        "strict": True,
                    },
                }
            if include_temp:
                kwargs_cc["temperature"] = 0.2

            try:
                logging.info(f"Attempting chat.completions (schema={include_schema}, temp={'on' if include_temp else 'off'})…")
                cc_resp = get_client().chat.completions.create(timeout=REQUEST_TIMEOUT, **kwargs_cc)
                path = "chat+schema" if include_schema else "chat+plain"
                return cc_resp, path, False
            except OpenAIError as oe_inner:
                msg_inner = str(oe_inner)
                if "temperature" in msg_inner and "unsupported" in msg_inner.lower() and include_temp:
                    logging.warning("Chat Completions: temperature unsupported; retrying without temperature…")
                    return chat_call(include_schema, False)
                raise

        try:
            return chat_call(True, True)
        except OpenAIError as oe2:
            # If JSON Schema unsupported, try plain JSON instruction (and handle temperature again)
            status2 = getattr(oe2, "status_code", None)
            msg2 = str(oe2)
            logging.warning(f"Chat Completions schema error (status {status2}): {msg2}. Retrying without response_format…")
            try:
                return chat_call(False, True)
            except OpenAIError as oe3:
                msg3 = str(oe3)
                if "temperature" in msg3 and "unsupported" in msg3.lower():
                    logging.warning("Chat Completions (no schema): temperature unsupported; retrying without temperature…")
                    return chat_call(False, False)
                raise

    # Gate web search by env (default on), and fall back if not available
    enable_web = os.getenv("ENABLE_WEB_SEARCH", "1").lower() in {"1", "true", "yes"}

    delay = 2
    for attempt in range(MAX_RETRIES):
        try:
            try:
                t0 = time.time()
                if force_chat:
                    logging.info("FORCE_CHAT_COMPLETIONS=1: Skipping Responses; using chat.completions path…")
                    resp, path_used, web_used = (get_client().chat.completions.create(
                        timeout=REQUEST_TIMEOUT,
                        model=MODEL,
                        messages=[
                            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
                            {"role": "user", "content": prompt},
                        ],
                    ), "chat+plain", False)
                else:
                    resp, path_used, web_used = do_request(enable_web)
            except OpenAIError as oe:
                # If web search is not enabled for the account/model, retry once without tools
                status = getattr(oe, "status_code", None)
                message = str(oe)
                if enable_web and (status == 400 or "web_search" in message.lower() or "tool" in message.lower()):
                    logging.warning("web_search tool unavailable; retrying without tools…")
                    t0 = time.time()
                    resp, path_used, web_used = do_request(False)
                else:
                    raise

            data = parse_response_to_json(resp)
            # Stats logging
            dt = time.time() - t0
            usage = extract_usage(resp)
            tokens_str = f"in={usage['in'] or '?'} out={usage['out'] or '?'} total={usage['total'] or '?'}"
            logging.info(
                f"⏱️ {dt:.2f}s | 🧠 tokens({tokens_str}) | 🧩 path={path_used} | 🔎 web_search={'on' if web_used else 'off'}"
            )

            # Fill Provider/Link if missing (safety)
            data.setdefault("Provider", provider)
            data.setdefault("Link", link)

            return data

        except RateLimitError:
            # Exponential backoff on rate limits
            if attempt == MAX_RETRIES - 1:
                raise
            logging.warning(f"Rate limit hit; backing off {delay}s (attempt {attempt+1}/{MAX_RETRIES}).")
            time.sleep(delay)
            delay = min(delay * 2, 30)

        except OpenAIError as e:
            # Retry transient issues; otherwise, break with placeholder
            if attempt < MAX_RETRIES - 1 and getattr(e, "status_code", 500) >= 500:
                logging.warning(f"OpenAIError {getattr(e, 'status_code', 'NA')}; retrying in {delay}s (attempt {attempt+1}/{MAX_RETRIES}).")
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            # For non-retryable errors, optionally avoid chat fallback if forced responses
            if force_responses:
                logging.error(f"❌ Non-retryable error with FORCE_RESPONSES=1 for {provider} | {link}: {e}")
            else:
                logging.error(f"❌ Non-retryable OpenAI error for {provider} | {link}: {e}")
            return placeholder_row(provider, link)
        except Exception as e:
            # Any unexpected error should not stop the batch
            logging.exception(f"Unexpected error for {provider} | {link}: {e}")
            return placeholder_row(provider, link)

    # Shouldn't reach here, but return placeholder if it does
    return placeholder_row(provider, link)


def main():
    setup_logging()
    if not os.getenv("OPENAI_API_KEY"):
        logging.error("OPENAI_API_KEY is not set in your environment.")
        sys.exit(1)

    # Optional health check before any processing
    skip_health = os.getenv("SKIP_OPENAI_HEALTH_CHECK", "0").lower() in {"1", "true", "yes"}
    if not skip_health:
        if not check_openai_health(MODEL):
            logging.error("Aborting due to OpenAI API health check failure. Set SKIP_OPENAI_HEALTH_CHECK=1 to bypass.")
            sys.exit(2)
    else:
        logging.info("Skipping OpenAI health check (SKIP_OPENAI_HEALTH_CHECK is set).")

    # Optionally clear output before running
    if os.getenv("CLEAR_OUTPUT_FILE", "0").lower() in {"1", "true", "yes"}:
        clear_output_file()
    else:
        ensure_output_header()
    # Link-based resume when not clearing output file
    already_links = load_processed_links()
    logging.info(f"Resume mode: {len(already_links)} links already in {OUTPUT_CSV}.")
    logging.info(f"Rate limiting: ~{RATE_LIMIT_RPM} rpm (per-request {PER_REQUEST_DELAY:.2f}s); batch size {BATCH_SIZE}, cooldown {BATCH_PAUSE_SECONDS}s.")

    # Use utf-8-sig to gracefully handle BOM-prefixed CSV headers
    with open(INPUT_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"Provider", "Link"}
        fieldnames = [fn.strip() for fn in (reader.fieldnames or [])]
        if not required.issubset(set(fieldnames)):
            logging.error(f"Input header detected: {fieldnames}")
            raise ValueError(f"Input must include columns: {sorted(required)}")

        # Snapshot only data rows (DictReader already excludes the header). Also drop fully blank lines.
        rows = [r for r in reader if not all(((v or "").strip() == "") for v in r.values())]
        to_process_total = sum(1 for r in rows if (r.get("Link") or "").strip() not in already_links)
        logging.info(
            f"Plan: process {to_process_total} of {len(rows)} input rows (skipping {len(rows) - to_process_total} existing)."
        )

        total = 0
        skipped = 0
        processed = 0
        batch_index = 0
        last_call_ts = 0.0  # epoch seconds

        for row in rows:
            total += 1
            provider = (row.get("Provider") or "").strip()
            link     = (row.get("Link") or "").strip()

            # Resume-skip if link already exists in output (link-only match)
            if link in already_links:
                skipped += 1
                logging.info(f"🔁 Skipping existing link, already in {OUTPUT_CSV}: {link}")
                continue

            # If missing critical fields, still emit a placeholder to keep parity
            if not provider or not link:
                append_row(placeholder_row(provider, link))
                processed += 1
                logging.info(f"Placeholder appended (missing fields): {provider} | {link}")
                continue

            # Per-request throttling: ensure minimum delay to honor rpm
            now = time.time()
            wait = max(0.0, (last_call_ts + PER_REQUEST_DELAY) - now)
            if wait > 0:
                logging.debug(f"Sleeping {wait:.2f}s to respect per-request limit.")
                time.sleep(wait)

            # Call model
            result = call_model(provider, link)
            last_call_ts = time.time()
            result = canonicalize_fields(result, provider, link)
            append_row(result)
            processed += 1
            logging.info(f"Processed: {provider} | {link}")

            # Batch cooldown after every BATCH_SIZE processed rows in this run
            if processed % BATCH_SIZE == 0:
                batch_index += 1
                logging.info(
                    f"Completed batch #{batch_index}: {processed}/{to_process_total} processed. Cooling down {BATCH_PAUSE_SECONDS}s…"
                )
                time.sleep(BATCH_PAUSE_SECONDS)

    logging.info(f"Done. Total rows: {total} | Skipped (resume): {skipped} | Newly processed: {processed}")


if __name__ == "__main__":
    main()
