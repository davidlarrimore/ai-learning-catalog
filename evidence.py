#!/usr/bin/env python3
import csv, os, time, pathlib, logging, re, json
from typing import Dict, Any, Set, Tuple, Optional, List

# Optional fuzzy library; fall back to stdlib if unavailable
try:
    from rapidfuzz import fuzz as _rf_fuzz
    def _similarity(a: str, b: str) -> int:
        return int(_rf_fuzz.token_set_ratio(a, b))
except Exception:
    import difflib
    def _similarity(a: str, b: str) -> int:
        return int(round(difflib.SequenceMatcher(None, a, b).ratio() * 100))

from dotenv import load_dotenv

# Load environment from a local .env file if present (non-destructive)
load_dotenv(override=False)

# ====== CONFIG (mirror originals where possible) ======
INPUT_CSV  = "input.csv"
OUTPUT_CSV = os.getenv("OUTPUT_CSV", os.path.join("data", "courses.csv"))
OUTPUT_JSON = os.getenv("OUTPUT_JSON", os.path.join("data", "courses.json"))

# Keep unused envs for backward compatibility with the codebase
MODEL = os.getenv("OPENAI_MODEL", "gpt-5")
MAX_RETRIES = 6
REQUEST_TIMEOUT = float(os.getenv("OPENAI_REQUEST_TIMEOUT", "60"))
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "1"))

# Rate limiting & batching (parsed but unused here; kept for compatibility)
RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "1"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))
BATCH_PAUSE_SECONDS = int(os.getenv("BATCH_PAUSE_SECONDS", "15"))
PER_REQUEST_DELAY = 60.0 / max(RATE_LIMIT_RPM, 1)

# CSV output headers (kept same order/style as original)
HEADERS = [
    "Provider","Link","Course Name","Summary","Track","Platform",
    "Hands On","Skill Level","Difficulty","Length","Evidence of Completion"
]

# Column override envs (new, optional, defaulting to the codebase’s headers)
PROVIDER_COLUMN = os.getenv("PROVIDER_COLUMN", "Provider")
COURSE_TITLE_COLUMN = os.getenv("COURSE_TITLE_COLUMN", "Course Title")  # not used, kept for future parity
EVIDENCE_COLUMN = os.getenv("EVIDENCE_COLUMN", "Evidence of Completion")

# Fuzzy threshold for matching providers
FUZZ_THRESHOLD = int(os.getenv("FUZZ_THRESHOLD", "85"))

# Allowed evidence values
EVIDENCE_ALLOWED = {
    "Certificate",
    "Screenshot of Completion Page",
    "Submit 2-3 sentence reflection Form",
}

# Canonical provider → evidence mapping (authoritative)
CANONICAL_TO_EVIDENCE: Dict[str, str] = {
    "Udemy": "Certificate",
    "Coursera (Audit Free)": "Certificate",
    "edX (Audit Free)": "Certificate",
    "Alison": "Certificate",
    "AWS Skill Builder": "Certificate",
    "Google Cloud Skills Boost": "Certificate",
    "Microsoft Learn AI Hub": "Certificate",
    "UiPath Academy": "Certificate",
    "UiPath": "Certificate",
    "Hugging Face Course": "Certificate",
    "LangChain Academy": "Certificate",
    "Google ML Crash Course": "Screenshot of Completion Page",
    "AWS AI Ready Free Courses": "Screenshot of Completion Page",
    "fast.ai": "Submit 2-3 sentence reflection Form",
    "YouTube": "Submit 2-3 sentence reflection Form",
    "GitHub – Data Science for Beginners": "Submit 2-3 sentence reflection Form",
}

# Alias heuristics (normalized) mapping to canonicals
_ALIAS_TO_CANONICAL = {
    # Udemy
    "udemy": "Udemy",
    "udemy com": "Udemy",

    # Coursera
    "coursera": "Coursera (Audit Free)",
    "coursera org": "Coursera (Audit Free)",
    "coursera (audit free)": "Coursera (Audit Free)",

    # edX
    "edx": "edX (Audit Free)",
    "edx org": "edX (Audit Free)",
    "edx (audit free)": "edX (Audit Free)",

    # Alison
    "alison": "Alison",
    "alison com": "Alison",

    # AWS Skill Builder
    "aws skill builder": "AWS Skill Builder",
    "skillbuilder aws": "AWS Skill Builder",
    "aws training": "AWS Skill Builder",
    "aws sb": "AWS Skill Builder",

    # Google Cloud Skills Boost
    "cloud skills boost": "Google Cloud Skills Boost",
    "google skills boost": "Google Cloud Skills Boost",
    "google cloud skills boost": "Google Cloud Skills Boost",
    "qwiklabs": "Google Cloud Skills Boost",

    # UiPath
    "uipath": "UiPath Academy",
    "uipath academy": "UiPath Academy",
    "academy uipath com": "UiPath Academy",

    # Microsoft Learn AI Hub
    "learn microsoft com": "Microsoft Learn AI Hub",
    "microsoft learn": "Microsoft Learn AI Hub",
    "ms learn": "Microsoft Learn AI Hub",
    "microsoft learn ai hub": "Microsoft Learn AI Hub",

    # Hugging Face Course
    "hugging face": "Hugging Face Course",
    "huggingface": "Hugging Face Course",
    "hf course": "Hugging Face Course",
    "hugging face course": "Hugging Face Course",

    # LangChain Academy
    "langchain academy": "LangChain Academy",
    "langchain": "LangChain Academy",

    # Google ML Crash Course
    "google ml crash course": "Google ML Crash Course",
    "mlcc": "Google ML Crash Course",
    "google developers machine learning crash course": "Google ML Crash Course",

    # AWS AI Ready Free Courses
    "aws ai ready": "AWS AI Ready Free Courses",
    "ai ready free courses": "AWS AI Ready Free Courses",
    "ai ready": "AWS AI Ready Free Courses",

    # fast.ai
    "fastai": "fast.ai",
    "fast ai": "fast.ai",
    "fast ai course": "fast.ai",
    "fast ai org": "fast.ai",

    # YouTube
    "youtube": "YouTube",
    "youtube com": "YouTube",
    "yt": "YouTube",

    # GitHub – Data Science for Beginners
    "data science for beginners": "GitHub – Data Science for Beginners",
    "microsoft data science for beginners": "GitHub – Data Science for Beginners",
    "github data science for beginners": "GitHub – Data Science for Beginners",
    "microsoft github data science for beginners": "GitHub – Data Science for Beginners",
}

_CANONICALS: List[str] = list(CANONICAL_TO_EVIDENCE.keys())


def setup_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
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
            reader = csv.DictReader(f)
            for r in reader:
                link = (r.get("Link", "") or "").strip()
                if link:
                    links.add(link)
    return links


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


_PUNCT_RE = re.compile(r"[\t\n\r\-_/\\.,:;!?'\"()\[\]{}|@#$%^&*+~=]+")


def _basic_normalize(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace(".com", " ").replace(".org", " ")
    s = _PUNCT_RE.sub(" ", s)
    s = " ".join(s.split())
    return s


def normalize_provider(raw: str) -> str:
    return _basic_normalize(raw)


def best_canonical_match(clean: str) -> Tuple[Optional[str], int]:
    if not clean:
        return None, 0

    # Alias exact match first
    if clean in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[clean], 100

    # Fuzzy over aliases and canonicals
    candidates: List[Tuple[str, str]] = []  # (display_name, canonical)
    for alias_norm, canon in _ALIAS_TO_CANONICAL.items():
        candidates.append((alias_norm, canon))
    for canon in _CANONICALS:
        candidates.append((canon.lower(), canon))

    best: List[Tuple[int, str]] = []  # (score, canonical)
    for disp, canon in candidates:
        score = _similarity(clean, disp)
        best.append((score, canon))

    # Keep best score(s)
    if not best:
        return None, 0
    max_score = max(s for s, _ in best)
    tied = [canon for s, canon in best if s == max_score]

    # Tie-breakers: prefer longer canonical name, then lexicographic
    tied = sorted(set(tied), key=lambda c: (-len(c), c))
    chosen = tied[0]
    return (chosen if max_score >= FUZZ_THRESHOLD else None), max_score


def evidence_for_provider(canonical: Optional[str]) -> str:
    if canonical and canonical in CANONICAL_TO_EVIDENCE:
        return CANONICAL_TO_EVIDENCE[canonical]
    return "Submit 2-3 sentence reflection Form"


def canonicalize_fields_passthrough(d: Dict[str, Any]) -> Dict[str, Any]:
    """Mirror original normalization where relevant; pass through other fields.
    Ensures required headers exist and coerces Evidence to allowed values.
    """
    # Start from defaults like original but prefer passthrough when present
    target = {
        "Provider": (d.get("Provider") or "").strip(),
        "Link": (d.get("Link") or "").strip(),
        "Course Name": (d.get("Course Name") or d.get("Course Title") or "Unknown").strip(),
        "Summary": (d.get("Summary") or "Unknown").strip(),
        "Track": (d.get("Track") or "").strip(),
        "Platform": (d.get("Platform") or "Unknown").strip(),
        "Hands On": (d.get("Hands On") or "Unknown").strip(),
        "Skill Level": (d.get("Skill Level") or "Unknown").strip(),
        "Difficulty": (d.get("Difficulty") or "Unknown").strip(),
        "Length": (d.get("Length") or "0 Hours").strip(),
        "Evidence of Completion": (d.get(EVIDENCE_COLUMN) or d.get("Evidence of Completion") or "").strip(),
    }

    # Coerce Length to "N Hours" integer form (mirror original behavior)
    def coerce_length(v: str) -> str:
        s = (v or "").strip()
        if s.isdigit():
            return f"{int(s)} Hours"
        num = "";
        for ch in s:
            if ch.isdigit():
                num += ch
            elif num:
                break
        return f"{int(num)} Hours" if num else "0 Hours"

    target["Length"] = coerce_length(target["Length"]) or "0 Hours"

    # Guarantee evidence is one of the allowed set
    ev = target.get("Evidence of Completion", "").strip()
    if ev not in EVIDENCE_ALLOWED:
        # Will be set by mapping outside; if still not set, default later
        pass

    # Collapse whitespace across string fields
    for k, v in list(target.items()):
        if isinstance(v, str):
            target[k] = " ".join(v.split())
    return target


def run_acceptance_tests():
    tests = [
        ("udemy.com", "Certificate"),
        ("Udemy", "Certificate"),
        ("Coursera", "Certificate"),
        ("Coursera (Audit Free)", "Certificate"),
        ("edx", "Certificate"),
        ("edx.org", "Certificate"),
        ("learn.microsoft.com", "Certificate"),
        ("Microsoft Learn", "Certificate"),
        ("Cloud Skills Boost", "Certificate"),
        ("Google Skills Boost", "Certificate"),
        ("Google ML Crash Course", "Screenshot of Completion Page"),
        ("MLCC", "Screenshot of Completion Page"),
        ("AWS AI Ready", "Screenshot of Completion Page"),
        ("AI Ready Free Courses", "Screenshot of Completion Page"),
        ("fastai", "Submit 2-3 sentence reflection Form"),
        ("fast.ai", "Submit 2-3 sentence reflection Form"),
        ("youtube.com", "Submit 2-3 sentence reflection Form"),
        ("YouTube", "Submit 2-3 sentence reflection Form"),
        ("microsoft data science for beginners (github)", "Submit 2-3 sentence reflection Form"),
        ("Acme Learning Hub", "Submit 2-3 sentence reflection Form"),
    ]
    for raw, expected in tests:
        clean = normalize_provider(raw)
        canon, score = best_canonical_match(clean)
        ev = evidence_for_provider(canon)
        logging.debug(f"TEST raw='{raw}' | norm='{clean}' | canon='{canon}' | score={score} | evidence='{ev}'")


def main():
    setup_logging()

    # Optional: acceptance tests when debugging
    if logging.getLogger().level <= logging.DEBUG:
        run_acceptance_tests()

    # Optionally clear output before running
    if os.getenv("CLEAR_OUTPUT_FILE", "0").lower() in {"1", "true", "yes"}:
        clear_output_file()
    else:
        ensure_output_header()

    already_links = load_processed_links()
    logging.info(f"Resume mode: {len(already_links)} links already in {OUTPUT_CSV}.")
    logging.info(f"Rate limiting (unused here): ~{RATE_LIMIT_RPM} rpm (per-request {PER_REQUEST_DELAY:.2f}s); batch size {BATCH_SIZE}, cooldown {BATCH_PAUSE_SECONDS}s.")

    total = 0
    skipped = 0
    processed = 0

    # Evidence counters
    counts = {
        "Certificate": 0,
        "Screenshot of Completion Page": 0,
        "Submit 2-3 sentence reflection Form": 0,
    }
    unmatched = 0

    # Use utf-8-sig to handle BOM-prefixed CSV headers
    with open(INPUT_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = [fn.strip() for fn in (reader.fieldnames or [])]
        required = {PROVIDER_COLUMN, "Link"}
        if not required.issubset(set(fieldnames)):
            logging.error(f"Input header detected: {fieldnames}")
            raise ValueError(f"Input must include columns: {sorted(required)}")

        rows = [r for r in reader if not all(((v or "").strip() == "") for v in r.values())]
        to_process_total = sum(1 for r in rows if (r.get("Link") or "").strip() not in already_links)
        logging.info(f"Plan: process {to_process_total} of {len(rows)} input rows (skipping {len(rows) - to_process_total} existing).")

        for r in rows:
            total += 1
            provider_raw = (r.get(PROVIDER_COLUMN) or r.get("Provider") or "").strip()
            link = (r.get("Link") or "").strip()

            if link in already_links:
                skipped += 1
                logging.info(f"🔁 Skipping existing link, already in {OUTPUT_CSV}: {link}")
                continue

            # Prepare base row with passthrough fields (mirrors original normalization style lightly)
            base = canonicalize_fields_passthrough(r)

            clean = normalize_provider(provider_raw)
            canon, score = best_canonical_match(clean)
            evidence = evidence_for_provider(canon)

            # Debug logging of mapping resolution
            logging.debug(
                f"Provider raw='{provider_raw}' → norm='{clean}' → canon='{canon}' (score={score}) → evidence='{evidence}'"
            )

            if not canon:
                unmatched += 1

            base[EVIDENCE_COLUMN] = evidence

            # Ensure exactly one of the allowed values
            if base[EVIDENCE_COLUMN] not in EVIDENCE_ALLOWED:
                base[EVIDENCE_COLUMN] = "Submit 2-3 sentence reflection Form"

            # Conform to repository’s fixed output headers
            out_row = {h: base.get(h, "") for h in HEADERS}
            append_row(out_row)
            counts[out_row[EVIDENCE_COLUMN]] = counts.get(out_row[EVIDENCE_COLUMN], 0) + 1
            processed += 1
            logging.info(f"Processed: {provider_raw} | {link}")

    # Summary
    logging.info(
        f"Done. Total rows: {total} | Skipped (resume): {skipped} | Newly processed: {processed}"
    )
    logging.info(
        f"Evidence counts: Certificate={counts['Certificate']}, Screenshot={counts['Screenshot of Completion Page']}, Reflection={counts['Submit 2-3 sentence reflection Form']} | Unmatched={unmatched}"
    )


if __name__ == "__main__":
    main()
