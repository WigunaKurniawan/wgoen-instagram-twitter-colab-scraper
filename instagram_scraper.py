import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import instaloader
from instaloader.exceptions import InstaloaderException, ProfileNotExistsException


DEFAULT_KEYWORDS = [
    "spmb",
    "pcmb",
    "pendaftaran",
    "pengumuman",
    "hasil seleksi",
    "jalur",
    "zonasi",
    "afirmasi",
    "domisili",
]

TEXT_RE = re.compile(r"\w", re.UNICODE)
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scrape Instagram post comments with Instaloader."
    )
    parser.add_argument("--username", required=True, help="Public Instagram username.")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--keywords",
        nargs="*",
        default=DEFAULT_KEYWORDS,
        help="Keyword list used to keep relevant comments.",
    )
    parser.add_argument(
        "--output-dir",
        default="output/instagram",
        help="Directory for CSV and JSON result files.",
    )
    parser.add_argument(
        "--max-posts",
        type=int,
        default=0,
        help="Optional max number of posts to inspect; 0 means all posts in range.",
    )
    parser.add_argument(
        "--sessionfile",
        default="",
        help="Optional Instaloader session file path for logged-in scraping.",
    )
    parser.add_argument(
        "--login-user",
        default="",
        help="Optional Instagram username that owns the session file.",
    )
    return parser.parse_args()


def normalize_text(value: str) -> str:
    value = value or ""
    value = re.sub(r"\s+", " ", value).strip()
    return value


def has_substantive_text(value: str) -> bool:
    return bool(TEXT_RE.search(value))


def contains_keyword(value: str, keywords: list[str]) -> bool:
    lowered = value.casefold()
    return any(keyword.casefold() in lowered for keyword in keywords)


def parse_date(value: str, end_of_day: bool = False) -> datetime:
    dt = datetime.strptime(value, "%Y-%m-%d")
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt.replace(tzinfo=timezone.utc)


def within_range(dt: datetime, start_dt: datetime, end_dt: datetime) -> bool:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return start_dt <= dt <= end_dt


def serialise_comment(post, comment) -> dict:
    owner = comment.owner
    return {
        "platform": "instagram",
        "profile_username": post.owner_username,
        "post_shortcode": post.shortcode,
        "post_url": f"https://www.instagram.com/p/{post.shortcode}/",
        "post_caption": normalize_text(post.caption or ""),
        "post_date_utc": post.date_utc.isoformat(),
        "comment_id": str(comment.id),
        "comment_text": normalize_text(comment.text),
        "comment_created_at_utc": comment.created_at_utc.isoformat(),
        "comment_owner_username": getattr(owner, "username", ""),
        "comment_owner_id": getattr(owner, "userid", ""),
        "like_count": getattr(comment, "likes_count", None),
        "is_answer": False,
        "parent_comment_id": "",
    }


def serialise_answer(post, parent_comment, answer) -> dict:
    owner = answer.owner
    return {
        "platform": "instagram",
        "profile_username": post.owner_username,
        "post_shortcode": post.shortcode,
        "post_url": f"https://www.instagram.com/p/{post.shortcode}/",
        "post_caption": normalize_text(post.caption or ""),
        "post_date_utc": post.date_utc.isoformat(),
        "comment_id": str(answer.id),
        "comment_text": normalize_text(answer.text),
        "comment_created_at_utc": answer.created_at_utc.isoformat(),
        "comment_owner_username": getattr(owner, "username", ""),
        "comment_owner_id": getattr(owner, "userid", ""),
        "like_count": getattr(answer, "likes_count", None),
        "is_answer": True,
        "parent_comment_id": str(parent_comment.id),
    }


def write_outputs(rows: list[dict], output_dir: Path, stem: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)

    fieldnames = list(rows[0].keys()) if rows else [
        "platform",
        "profile_username",
        "post_shortcode",
        "post_url",
        "post_caption",
        "post_date_utc",
        "comment_id",
        "comment_text",
        "comment_created_at_utc",
        "comment_owner_username",
        "comment_owner_id",
        "like_count",
        "is_answer",
        "parent_comment_id",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    start_dt = parse_date(args.start_date)
    end_dt = parse_date(args.end_date, end_of_day=True)
    output_dir = Path(args.output_dir)
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=False,
    )

    if args.sessionfile and args.login_user:
        loader.load_session_from_file(args.login_user, args.sessionfile)

    try:
        profile = instaloader.Profile.from_username(loader.context, args.username)
    except ProfileNotExistsException as exc:
        print(
            "Instagram profile could not be resolved. Double-check the username or "
            "run again with --sessionfile and --login-user because public requests can be blocked."
        )
        return
    except InstaloaderException as exc:
        print(
            "Instagram request was blocked before scraping comments. "
            "Try again with a logged-in session file."
        )
        return
    seen_text = Counter()
    rows: list[dict] = []
    inspected_posts = 0

    for post in profile.get_posts():
        inspected_posts += 1
        if args.max_posts and inspected_posts > args.max_posts:
            break

        try:
            comments_iterable = post.get_comments()
        except InstaloaderException as exc:
            print(f"Skipping post {post.shortcode}: {exc}")
            continue

        for comment in comments_iterable:
            text = normalize_text(comment.text)
            if not within_range(comment.created_at_utc, start_dt, end_dt):
                continue
            if not has_substantive_text(text):
                continue
            if not contains_keyword(text, args.keywords):
                continue
            dedupe_key = text.casefold()
            seen_text[dedupe_key] += 1
            if seen_text[dedupe_key] > 1:
                continue
            rows.append(serialise_comment(post, comment))

            for answer in comment.answers or []:
                answer_text = normalize_text(answer.text)
                if not within_range(answer.created_at_utc, start_dt, end_dt):
                    continue
                if not has_substantive_text(answer_text):
                    continue
                if not contains_keyword(answer_text, args.keywords):
                    continue
                answer_dedupe_key = answer_text.casefold()
                seen_text[answer_dedupe_key] += 1
                if seen_text[answer_dedupe_key] > 1:
                    continue
                rows.append(serialise_answer(post, comment, answer))

    stem = f"{args.username}_{args.start_date}_to_{args.end_date}"
    write_outputs(rows, output_dir, stem)
    print(f"Saved {len(rows)} Instagram comments/replies into {output_dir.resolve()}")


if __name__ == "__main__":
    main()
