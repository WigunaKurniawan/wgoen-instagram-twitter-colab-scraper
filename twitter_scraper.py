import argparse
import csv
from datetime import datetime, timedelta, timezone
import importlib
import importlib.machinery
import json
import re
from collections import Counter
from pathlib import Path


def _compat_find_module(self, fullname, path=None):
    spec = self.find_spec(fullname, path)
    return spec.loader if spec else None


finder_classes = [importlib.machinery.FileFinder]
bootstrap_external = getattr(importlib, "_bootstrap_external", None)
if bootstrap_external and getattr(bootstrap_external, "FileFinder", None):
    finder_classes.append(bootstrap_external.FileFinder)

for finder_class in finder_classes:
    if not hasattr(finder_class, "find_module"):
        finder_class.find_module = _compat_find_module

try:
    import snscrape.modules.twitter as sntwitter
except Exception:  # pragma: no cover - optional dependency at runtime
    sntwitter = None


DEFAULT_HASHTAGS = [
    "#SPMB2026",
    "#PCMB2026",
    "#SPMBJabar",
    "#PCMBError",
    "#SPMBGagal",
]
DEFAULT_PHRASES = [
    "SPMB Jabar",
    "PCMB Jabar",
    "system error",
    "sistem error SPMB",
    "pengumuman molor",
    "SPMB down",
]
DEFAULT_BOOLEAN_SNIPPETS = [
    "SPMB (error OR down OR gagal OR lambat)",
    "PCMB (pengumuman OR hasil OR \"tidak bisa akses\")",
]

DEFAULT_FIELDNAMES = [
    "platform",
    "source_mode",
    "source_query",
    "tweet_id",
    "tweet_url",
    "created_at_utc",
    "username",
    "display_name",
    "user_id",
    "content",
    "reply_count",
    "retweet_count",
    "like_count",
    "quote_count",
    "lang",
    "is_reply",
    "in_reply_to_tweet_id",
    "hashtags",
]

TEXT_RE = re.compile(r"\w", re.UNICODE)
URL_ONLY_RE = re.compile(r"^(https?://\S+|www\.\S+)+$", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare Twitter/X output using a stable manual-import path by default, "
            "with optional experimental snscrape mode."
        )
    )
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--output-dir",
        default="output/twitter",
        help="Directory for CSV and JSON result files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional result cap after filtering; 0 means no cap.",
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "manual_csv", "manual_json", "snscrape_experimental"],
        default="auto",
        help="Collection mode. Default auto prefers manual import when input file is provided.",
    )
    parser.add_argument(
        "--input-file",
        default="",
        help="Optional manual input file (.csv or .json) exported or prepared from browser-assisted collection.",
    )
    parser.add_argument(
        "--hashtags",
        nargs="*",
        default=DEFAULT_HASHTAGS,
        help="Hashtags used inside generated search queries for snscrape experimental mode.",
    )
    parser.add_argument(
        "--phrases",
        nargs="*",
        default=DEFAULT_PHRASES,
        help="Exact phrases used inside generated search queries for snscrape experimental mode.",
    )
    parser.add_argument(
        "--boolean-snippets",
        nargs="*",
        default=DEFAULT_BOOLEAN_SNIPPETS,
        help="Additional boolean search snippets for snscrape experimental mode.",
    )
    return parser.parse_args()


def normalize_text(value: str) -> str:
    value = value or ""
    return re.sub(r"\s+", " ", value).strip()


def has_substantive_text(value: str) -> bool:
    return bool(TEXT_RE.search(value))


def is_link_only(value: str) -> bool:
    return bool(URL_ONLY_RE.fullmatch(value.replace(" ", "")))


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(cleaned)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(cleaned, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_range_date(value: str, end_of_day: bool = False) -> datetime:
    dt = datetime.strptime(value, "%Y-%m-%d")
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt.replace(tzinfo=timezone.utc)


def within_range(dt: datetime | None, start_dt: datetime, end_dt: datetime) -> bool:
    if dt is None:
        return False
    return start_dt <= dt <= end_dt


def build_queries(
    start_date: str, end_date: str, hashtags: list[str], phrases: list[str], snippets: list[str]
) -> list[str]:
    until_date = (
        datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    ).strftime("%Y-%m-%d")
    hashtag_query = " OR ".join(hashtags)
    phrase_query = " OR ".join(f'"{phrase}"' for phrase in phrases)
    queries = []
    if hashtag_query:
        queries.append(f"({hashtag_query}) since:{start_date} until:{until_date}")
    if phrase_query:
        queries.append(f"({phrase_query}) since:{start_date} until:{until_date}")
    for snippet in snippets:
        queries.append(f"({snippet}) since:{start_date} until:{until_date}")
    return queries


def serialise_tweet(tweet, source_query: str) -> dict:
    return {
        "platform": "twitter",
        "source_mode": "snscrape_experimental",
        "source_query": source_query,
        "tweet_id": str(tweet.id),
        "tweet_url": tweet.url,
        "created_at_utc": tweet.date.isoformat(),
        "username": getattr(tweet.user, "username", ""),
        "display_name": getattr(tweet.user, "displayname", ""),
        "user_id": getattr(tweet.user, "id", ""),
        "content": normalize_text(tweet.rawContent),
        "reply_count": tweet.replyCount,
        "retweet_count": tweet.retweetCount,
        "like_count": tweet.likeCount,
        "quote_count": tweet.quoteCount,
        "lang": tweet.lang,
        "is_reply": bool(tweet.inReplyToTweetId),
        "in_reply_to_tweet_id": tweet.inReplyToTweetId or "",
        "hashtags": ",".join(tweet.hashtags or []),
    }


def field_value(row: dict, *keys: str) -> str:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return str(row[key])
    return ""


def normalize_manual_row(row: dict) -> dict:
    content = normalize_text(field_value(row, "content", "text", "tweet_text", "rawContent"))
    hashtags = field_value(row, "hashtags", "tag_list")
    created_at = field_value(row, "created_at_utc", "created_at", "date", "tweet_date")
    created_dt = parse_iso_datetime(created_at)
    return {
        "platform": "twitter",
        "source_mode": field_value(row, "source_mode") or "manual_import",
        "source_query": field_value(row, "source_query", "query"),
        "tweet_id": field_value(row, "tweet_id", "id"),
        "tweet_url": field_value(row, "tweet_url", "url", "link"),
        "created_at_utc": created_dt.isoformat() if created_dt else created_at,
        "username": field_value(row, "username", "user_handle", "screen_name"),
        "display_name": field_value(row, "display_name", "name", "user_name"),
        "user_id": field_value(row, "user_id", "author_id"),
        "content": content,
        "reply_count": field_value(row, "reply_count", "replies") or 0,
        "retweet_count": field_value(row, "retweet_count", "retweets") or 0,
        "like_count": field_value(row, "like_count", "likes") or 0,
        "quote_count": field_value(row, "quote_count", "quotes") or 0,
        "lang": field_value(row, "lang", "language"),
        "is_reply": str(field_value(row, "is_reply")).lower() in {"1", "true", "yes"},
        "in_reply_to_tweet_id": field_value(row, "in_reply_to_tweet_id", "parent_tweet_id"),
        "hashtags": hashtags,
    }


def load_manual_rows(path: Path) -> list[dict]:
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [normalize_manual_row(row) for row in csv.DictReader(handle)]
    if path.suffix.lower() == ".json":
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            payload = payload.get("rows", [])
        return [normalize_manual_row(row) for row in payload]
    raise ValueError("Manual input file must be .csv or .json")


def filter_rows(rows: list[dict], start_dt: datetime, end_dt: datetime, limit: int) -> list[dict]:
    seen_ids: set[str] = set()
    seen_text = Counter()
    filtered: list[dict] = []

    for row in rows:
        content = normalize_text(row.get("content", ""))
        if not has_substantive_text(content):
            continue
        if is_link_only(content):
            continue

        created_dt = parse_iso_datetime(str(row.get("created_at_utc", "")))
        if created_dt and not within_range(created_dt, start_dt, end_dt):
            continue

        dedupe_key = content.casefold()
        seen_text[dedupe_key] += 1
        if seen_text[dedupe_key] > 1:
            continue

        tweet_id = str(row.get("tweet_id", "")).strip()
        if tweet_id and tweet_id in seen_ids:
            continue
        if tweet_id:
            seen_ids.add(tweet_id)

        filtered.append(row)
        if limit and len(filtered) >= limit:
            break
    return filtered


def write_outputs(rows: list[dict], output_dir: Path, stem: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)

    fieldnames = list(rows[0].keys()) if rows else DEFAULT_FIELDNAMES
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_error_report(errors: list[dict], output_dir: Path, stem: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    error_path = output_dir / f"{stem}_errors.json"
    with error_path.open("w", encoding="utf-8") as handle:
        json.dump(errors, handle, ensure_ascii=False, indent=2)


def detect_mode(args: argparse.Namespace) -> str:
    if args.mode != "auto":
        return args.mode
    if args.input_file:
        suffix = Path(args.input_file).suffix.lower()
        if suffix == ".csv":
            return "manual_csv"
        if suffix == ".json":
            return "manual_json"
    return "snscrape_experimental"


def run_manual_mode(args: argparse.Namespace, mode: str) -> tuple[list[dict], list[dict]]:
    if not args.input_file:
        raise ValueError("Manual mode requires --input-file pointing to a CSV or JSON file.")
    input_path = Path(args.input_file)
    rows = load_manual_rows(input_path)
    start_dt = parse_range_date(args.start_date)
    end_dt = parse_range_date(args.end_date, end_of_day=True)
    filtered = filter_rows(rows, start_dt, end_dt, args.limit)
    notes = [
        {
            "mode": mode,
            "note": (
                "Rows were normalized from a manual or browser-assisted input file. "
                "This is the recommended stable path when public X/Twitter search endpoints are unreliable."
            ),
            "input_file": str(input_path),
        }
    ]
    return filtered, notes


def run_snscrape_mode(args: argparse.Namespace) -> tuple[list[dict], list[dict]]:
    if sntwitter is None:
        return [], [
            {
                "mode": "snscrape_experimental",
                "error": "snscrape is not installed in this environment.",
                "recommendation": "Use manual_csv or manual_json mode instead.",
            }
        ]

    rows: list[dict] = []
    query_errors: list[dict] = []
    seen_ids: set[str] = set()
    seen_text = Counter()
    queries = build_queries(
        args.start_date,
        args.end_date,
        args.hashtags,
        args.phrases,
        args.boolean_snippets,
    )

    for query in queries:
        try:
            for tweet in sntwitter.TwitterSearchScraper(query).get_items():
                content = normalize_text(tweet.rawContent)
                if not has_substantive_text(content):
                    continue
                if is_link_only(content):
                    continue
                if tweet.retweetedTweet and not content:
                    continue

                dedupe_key = content.casefold()
                seen_text[dedupe_key] += 1
                if seen_text[dedupe_key] > 1:
                    continue

                tweet_id = str(tweet.id)
                if tweet_id in seen_ids:
                    continue

                seen_ids.add(tweet_id)
                rows.append(serialise_tweet(tweet, query))
                if args.limit and len(rows) >= args.limit:
                    break
        except Exception as exc:
            query_errors.append(
                {
                    "mode": "snscrape_experimental",
                    "query": query,
                    "error": str(exc),
                    "recommendation": (
                        "Public X/Twitter search endpoints are unstable. "
                        "Switch to manual_csv or manual_json mode for a more reliable flow."
                    ),
                }
            )
            print(f"Query failed and was skipped: {query}")
        if args.limit and len(rows) >= args.limit:
            break

    return rows, query_errors


def main() -> None:
    args = parse_args()
    mode = detect_mode(args)

    if mode in {"manual_csv", "manual_json"}:
        rows, notes = run_manual_mode(args, mode)
    else:
        rows, notes = run_snscrape_mode(args)

    stem = f"twitter_{args.start_date}_to_{args.end_date}"
    output_dir = Path(args.output_dir)
    write_outputs(rows, output_dir, stem)
    if notes:
        write_error_report(notes, output_dir, stem)
    print(f"Saved {len(rows)} tweets/replies into {output_dir.resolve()} using mode={mode}")


if __name__ == "__main__":
    main()
