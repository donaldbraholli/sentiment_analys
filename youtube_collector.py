from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


# ------------------------------------------------------------
# Setup
# ------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def get_database_path() -> str:
    """
    Tries to find the database path from:
    1. .env DATABASE_PATH
    2. config.py DB_PATH
    3. config.py DATABASE_PATH
    4. fallback: customer_sentiment.db
    """
    env_path = os.getenv("DATABASE_PATH")
    if env_path:
        return env_path

    try:
        import config

        if hasattr(config, "DB_PATH"):
            return str(config.DB_PATH)

        if hasattr(config, "DATABASE_PATH"):
            return str(config.DATABASE_PATH)

    except Exception:
        pass

    return str(PROJECT_ROOT / "customer_sentiment.db")


DB_PATH = get_database_path()


YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_COMMENT_THREADS_URL = "https://www.googleapis.com/youtube/v3/commentThreads"


@dataclass
class YouTubeFetchSummary:
    company_id: int
    status: str
    videos_found: int = 0
    comments_found: int = 0
    replies_found: int = 0
    entries_inserted: int = 0
    entries_updated: int = 0
    skipped_reason: str | None = None
    error_message: str | None = None


class YouTubeApiError(RuntimeError):
    def __init__(self, message: str, reason: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code


# ------------------------------------------------------------
# Utility helpers
# ------------------------------------------------------------

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def safe_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return value


def hash_youtube_author(author_value: str | None) -> str | None:
    """
    Stores a stable hash instead of raw YouTube author/channel identity.

    Prefer authorChannelId when available.
    Fallback to display name.
    """
    if not author_value:
        return None

    author_value = str(author_value).strip()

    if not author_value:
        return None

    salt = os.getenv("AUTHOR_HASH_SALT", "customer_sentiment_default_salt")
    raw = f"{salt}:{author_value}".encode("utf-8")

    return hashlib.sha256(raw).hexdigest()


def get_api_key() -> str:
    api_key = os.getenv("YOUTUBE_API_KEY")

    if api_key:
        api_key = api_key.strip().strip('"').strip("'")

    if not api_key:
        raise RuntimeError("Missing YOUTUBE_API_KEY. Add it to your .env file.")

    return api_key


# ------------------------------------------------------------
# Database
# ------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_youtube_tables(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS youtube_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        company_id INTEGER NOT NULL,

        youtube_id TEXT NOT NULL,
        topic_id TEXT NOT NULL,
        parent_comment_id TEXT,

        entry_type TEXT NOT NULL CHECK(entry_type IN ('video', 'comment', 'reply')),

        channel_id TEXT,
        channel_title TEXT,

        title TEXT,
        body TEXT,
        permalink TEXT,

        author_hash TEXT,

        like_count INTEGER DEFAULT 0,
        reply_count INTEGER DEFAULT 0,

        youtube_published_at TEXT,
        collected_at TEXT NOT NULL,
        updated_at TEXT,

        is_relevant INTEGER DEFAULT 1,
        service_category TEXT,
        sentiment TEXT,
        sentiment_score REAL,
        analysis_summary TEXT,

        source TEXT DEFAULT 'youtube',

        UNIQUE(company_id, youtube_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS youtube_fetch_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        company_id INTEGER NOT NULL,

        started_at TEXT NOT NULL,
        finished_at TEXT,

        status TEXT NOT NULL,
        error_message TEXT,

        videos_found INTEGER DEFAULT 0,
        comments_found INTEGER DEFAULT 0,
        replies_found INTEGER DEFAULT 0,
        entries_inserted INTEGER DEFAULT 0,
        entries_updated INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS youtube_query_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        company_id INTEGER NOT NULL,

        query TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,

        created_at TEXT NOT NULL,

        UNIQUE(company_id, query)
    )
    """)

    conn.commit()


def entry_exists(conn: sqlite3.Connection, company_id: int, youtube_id: str) -> bool:
    cur = conn.cursor()

    cur.execute(
        """
        SELECT 1
        FROM youtube_entries
        WHERE company_id = ?
          AND youtube_id = ?
        LIMIT 1
        """,
        (company_id, youtube_id),
    )

    return cur.fetchone() is not None


def upsert_youtube_entry(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    youtube_id: str,
    topic_id: str,
    parent_comment_id: str | None,
    entry_type: str,
    channel_id: str | None,
    channel_title: str | None,
    title: str | None,
    body: str | None,
    permalink: str | None,
    author_hash: str | None,
    like_count: int,
    reply_count: int,
    youtube_published_at: str | None,
) -> str:
    existed_before = entry_exists(conn, company_id, youtube_id)

    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO youtube_entries (
            company_id,
            youtube_id,
            topic_id,
            parent_comment_id,
            entry_type,
            channel_id,
            channel_title,
            title,
            body,
            permalink,
            author_hash,
            like_count,
            reply_count,
            youtube_published_at,
            collected_at,
            updated_at,
            source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'youtube')
        ON CONFLICT(company_id, youtube_id)
        DO UPDATE SET
            topic_id = excluded.topic_id,
            parent_comment_id = excluded.parent_comment_id,
            entry_type = excluded.entry_type,
            channel_id = excluded.channel_id,
            channel_title = excluded.channel_title,
            title = excluded.title,
            body = excluded.body,
            permalink = excluded.permalink,
            author_hash = excluded.author_hash,
            like_count = excluded.like_count,
            reply_count = excluded.reply_count,
            youtube_published_at = excluded.youtube_published_at,
            updated_at = excluded.updated_at
        """,
        (
            company_id,
            youtube_id,
            topic_id,
            parent_comment_id,
            entry_type,
            channel_id,
            channel_title,
            title,
            body,
            permalink,
            author_hash,
            like_count,
            reply_count,
            youtube_published_at,
            now_utc_iso(),
            now_utc_iso(),
        ),
    )

    conn.commit()

    return "updated" if existed_before else "inserted"


def add_youtube_query_rule(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    query: str,
) -> None:
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO youtube_query_rules (
            company_id,
            query,
            enabled,
            created_at
        )
        VALUES (?, ?, 1, ?)
        ON CONFLICT(company_id, query)
        DO UPDATE SET
            enabled = 1
        """,
        (
            company_id,
            query,
            now_utc_iso(),
        ),
    )

    conn.commit()


def get_enabled_youtube_rules(conn: sqlite3.Connection, company_id: int) -> list[sqlite3.Row]:
    cur = conn.cursor()

    cur.execute(
        """
        SELECT query
        FROM youtube_query_rules
        WHERE company_id = ?
          AND enabled = 1
        ORDER BY id ASC
        """,
        (company_id,),
    )

    return cur.fetchall()


def get_last_successful_run(conn: sqlite3.Connection, company_id: int) -> sqlite3.Row | None:
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM youtube_fetch_runs
        WHERE company_id = ?
          AND status = 'success'
          AND finished_at IS NOT NULL
        ORDER BY finished_at DESC
        LIMIT 1
        """,
        (company_id,),
    )

    return cur.fetchone()


def can_run_youtube_fetch(
    conn: sqlite3.Connection,
    company_id: int,
    *,
    min_hours_between_runs: int = 24,
) -> tuple[bool, str | None]:
    last_run = get_last_successful_run(conn, company_id)

    if last_run is None:
        return True, None

    last_finished_at = parse_iso_datetime(last_run["finished_at"])
    next_allowed_at = last_finished_at + timedelta(hours=min_hours_between_runs)

    if datetime.now(timezone.utc) >= next_allowed_at:
        return True, None

    return False, f"Last successful YouTube fetch was less than {min_hours_between_runs} hours ago."


def start_fetch_run(conn: sqlite3.Connection, company_id: int) -> int:
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO youtube_fetch_runs (
            company_id,
            started_at,
            status
        )
        VALUES (?, ?, 'running')
        """,
        (
            company_id,
            now_utc_iso(),
        ),
    )

    conn.commit()

    return int(cur.lastrowid)


def finish_fetch_run(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    status: str,
    error_message: str | None = None,
    videos_found: int = 0,
    comments_found: int = 0,
    replies_found: int = 0,
    entries_inserted: int = 0,
    entries_updated: int = 0,
) -> None:
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE youtube_fetch_runs
        SET
            finished_at = ?,
            status = ?,
            error_message = ?,
            videos_found = ?,
            comments_found = ?,
            replies_found = ?,
            entries_inserted = ?,
            entries_updated = ?
        WHERE id = ?
        """,
        (
            now_utc_iso(),
            status,
            error_message,
            videos_found,
            comments_found,
            replies_found,
            entries_inserted,
            entries_updated,
            run_id,
        ),
    )

    conn.commit()


# ------------------------------------------------------------
# YouTube API helpers
# ------------------------------------------------------------

def youtube_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    params = dict(params)
    params["key"] = get_api_key()

    response = requests.get(url, params=params, timeout=30)

    try:
        data = response.json()
    except Exception:
        data = {}

    if response.status_code >= 400:
        error = data.get("error", {})
        message = error.get("message", f"YouTube API error: HTTP {response.status_code}")

        errors = error.get("errors") or []
        reason = None

        if errors and isinstance(errors, list):
            reason = errors[0].get("reason")

        raise YouTubeApiError(
            message=message,
            reason=reason,
            status_code=response.status_code,
        )

    return data


def search_videos(query: str, *, max_results: int) -> list[dict[str, Any]]:
    region_code = os.getenv("YOUTUBE_REGION_CODE", "IE").strip() or "IE"

    max_results = max(1, min(max_results, 50))

    data = youtube_get(
        YOUTUBE_SEARCH_URL,
        {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "date",
            "maxResults": max_results,
            "regionCode": region_code,
            "safeSearch": "none",
        },
    )

    return data.get("items", [])


def get_video_comments(video_id: str, *, max_results: int) -> list[dict[str, Any]]:
    max_results = max(1, min(max_results, 100))

    data = youtube_get(
        YOUTUBE_COMMENT_THREADS_URL,
        {
            "part": "snippet,replies",
            "videoId": video_id,
            "order": "time",
            "maxResults": max_results,
            "textFormat": "plainText",
        },
    )

    return data.get("items", [])


# ------------------------------------------------------------
# Save logic
# ------------------------------------------------------------

def save_video(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    video_item: dict[str, Any],
) -> str | None:
    video_id = video_item.get("id", {}).get("videoId")

    if not video_id:
        return None

    snippet = video_item.get("snippet", {})

    permalink = f"https://www.youtube.com/watch?v={video_id}"

    return upsert_youtube_entry(
        conn,
        company_id=company_id,
        youtube_id=video_id,
        topic_id=video_id,
        parent_comment_id=None,
        entry_type="video",
        channel_id=safe_text(snippet.get("channelId")),
        channel_title=safe_text(snippet.get("channelTitle")),
        title=safe_text(snippet.get("title")),
        body=safe_text(snippet.get("description")),
        permalink=permalink,
        author_hash=None,
        like_count=0,
        reply_count=0,
        youtube_published_at=safe_text(snippet.get("publishedAt")),
    )


def get_author_hash_from_comment_snippet(snippet: dict[str, Any]) -> str | None:
    author_channel_id = snippet.get("authorChannelId", {})

    if isinstance(author_channel_id, dict):
        channel_value = author_channel_id.get("value")

        if channel_value:
            return hash_youtube_author(channel_value)

    return hash_youtube_author(snippet.get("authorDisplayName"))


def save_comment(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    video_id: str,
    comment_id: str,
    comment_snippet: dict[str, Any],
    parent_comment_id: str | None,
    entry_type: str,
) -> str | None:
    body = safe_text(comment_snippet.get("textDisplay") or comment_snippet.get("textOriginal"))

    if not body:
        return None

    permalink = f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}"

    return upsert_youtube_entry(
        conn,
        company_id=company_id,
        youtube_id=comment_id,
        topic_id=video_id,
        parent_comment_id=parent_comment_id,
        entry_type=entry_type,
        channel_id=None,
        channel_title=None,
        title=None,
        body=body,
        permalink=permalink,
        author_hash=get_author_hash_from_comment_snippet(comment_snippet),
        like_count=int(comment_snippet.get("likeCount", 0) or 0),
        reply_count=int(comment_snippet.get("totalReplyCount", 0) or 0),
        youtube_published_at=safe_text(comment_snippet.get("publishedAt")),
    )


def save_comment_thread(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    video_id: str,
    thread_item: dict[str, Any],
) -> tuple[int, int, int, int]:
    """
    Returns:
    comments_found, replies_found, entries_inserted, entries_updated
    """
    comments_found = 0
    replies_found = 0
    entries_inserted = 0
    entries_updated = 0

    snippet = thread_item.get("snippet", {})
    top_comment = snippet.get("topLevelComment", {})
    top_comment_id = top_comment.get("id")
    top_comment_snippet = top_comment.get("snippet", {})

    if top_comment_id:
        result = save_comment(
            conn,
            company_id=company_id,
            video_id=video_id,
            comment_id=top_comment_id,
            comment_snippet=top_comment_snippet,
            parent_comment_id=None,
            entry_type="comment",
        )

        if result:
            comments_found += 1

            if result == "inserted":
                entries_inserted += 1
            elif result == "updated":
                entries_updated += 1

    replies = thread_item.get("replies", {}).get("comments", [])

    for reply in replies:
        reply_id = reply.get("id")
        reply_snippet = reply.get("snippet", {})

        if not reply_id:
            continue

        result = save_comment(
            conn,
            company_id=company_id,
            video_id=video_id,
            comment_id=reply_id,
            comment_snippet=reply_snippet,
            parent_comment_id=top_comment_id,
            entry_type="reply",
        )

        if result:
            replies_found += 1

            if result == "inserted":
                entries_inserted += 1
            elif result == "updated":
                entries_updated += 1

    return comments_found, replies_found, entries_inserted, entries_updated


# ------------------------------------------------------------
# Main collection logic
# ------------------------------------------------------------

def collect_youtube_for_company(
    company_id: int,
    *,
    max_videos_per_rule: int = 5,
    max_comments_per_video: int = 50,
    min_hours_between_runs: int | None = None,
    force: bool = False,
) -> YouTubeFetchSummary:
    if min_hours_between_runs is None:
        min_hours_between_runs = int(os.getenv("YOUTUBE_DAILY_LIMIT_HOURS", "24"))

    conn = get_connection()
    ensure_youtube_tables(conn)

    can_run, skipped_reason = can_run_youtube_fetch(
        conn,
        company_id,
        min_hours_between_runs=min_hours_between_runs,
    )

    if not can_run and not force:
        conn.close()

        return YouTubeFetchSummary(
            company_id=company_id,
            status="skipped",
            skipped_reason=skipped_reason,
        )

    rules = get_enabled_youtube_rules(conn, company_id)

    if not rules:
        conn.close()

        return YouTubeFetchSummary(
            company_id=company_id,
            status="skipped",
            skipped_reason="No enabled YouTube query rules found for this company.",
        )

    run_id = start_fetch_run(conn, company_id)

    summary = YouTubeFetchSummary(
        company_id=company_id,
        status="running",
    )

    try:
        for rule in rules:
            query = rule["query"]

            videos = search_videos(
                query,
                max_results=max_videos_per_rule,
            )

            for video_item in videos:
                video_id = video_item.get("id", {}).get("videoId")

                if not video_id:
                    continue

                video_result = save_video(
                    conn,
                    company_id=company_id,
                    video_item=video_item,
                )

                if video_result:
                    summary.videos_found += 1

                    if video_result == "inserted":
                        summary.entries_inserted += 1
                    elif video_result == "updated":
                        summary.entries_updated += 1

                try:
                    comment_threads = get_video_comments(
                        video_id,
                        max_results=max_comments_per_video,
                    )

                except YouTubeApiError as exc:
                    # Some videos have comments disabled. That should not fail the whole run.
                    if exc.reason in {"commentsDisabled", "videoNotFound", "forbidden"}:
                        continue

                    raise

                for thread_item in comment_threads:
                    comments_found, replies_found, inserts, updates = save_comment_thread(
                        conn,
                        company_id=company_id,
                        video_id=video_id,
                        thread_item=thread_item,
                    )

                    summary.comments_found += comments_found
                    summary.replies_found += replies_found
                    summary.entries_inserted += inserts
                    summary.entries_updated += updates

        summary.status = "success"

        finish_fetch_run(
            conn,
            run_id=run_id,
            status="success",
            videos_found=summary.videos_found,
            comments_found=summary.comments_found,
            replies_found=summary.replies_found,
            entries_inserted=summary.entries_inserted,
            entries_updated=summary.entries_updated,
        )

    except Exception as exc:
        summary.status = "failed"
        summary.error_message = str(exc)

        finish_fetch_run(
            conn,
            run_id=run_id,
            status="failed",
            error_message=summary.error_message,
            videos_found=summary.videos_found,
            comments_found=summary.comments_found,
            replies_found=summary.replies_found,
            entries_inserted=summary.entries_inserted,
            entries_updated=summary.entries_updated,
        )

    finally:
        conn.close()

    return summary


# ------------------------------------------------------------
# Demo seed rules
# ------------------------------------------------------------

def seed_vodafone_ireland_youtube_rules(company_id: int) -> None:
    conn = get_connection()
    ensure_youtube_tables(conn)

    queries = [
        "Vodafone Ireland",
        "Vodafone Ireland broadband",
        "Vodafone Ireland mobile",
        "Vodafone Ireland 5G",
        "Vodafone Ireland roaming",
        "Vodafone Ireland customer service",
        "Vodafone Ireland app",
        "Vodafone Ireland outage",
        "vodafone.ie",
    ]

    for query in queries:
        add_youtube_query_rule(
            conn,
            company_id=company_id,
            query=query,
        )

    conn.close()


def print_summary(summary: YouTubeFetchSummary) -> None:
    print("")
    print("YouTube fetch summary")
    print("---------------------")
    print(f"Company ID:       {summary.company_id}")
    print(f"Status:           {summary.status}")
    print(f"Videos found:     {summary.videos_found}")
    print(f"Comments found:   {summary.comments_found}")
    print(f"Replies found:    {summary.replies_found}")
    print(f"Inserted:         {summary.entries_inserted}")
    print(f"Updated:          {summary.entries_updated}")

    if summary.skipped_reason:
        print(f"Skipped reason:   {summary.skipped_reason}")

    if summary.error_message:
        print(f"Error:            {summary.error_message}")

    print("")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect YouTube sentiment data.")

    parser.add_argument(
        "--company-id",
        type=int,
        required=True,
        help="Company ID from your companies table.",
    )

    parser.add_argument(
        "--videos",
        type=int,
        default=5,
        help="Maximum YouTube videos to fetch per query rule.",
    )

    parser.add_argument(
        "--comments",
        type=int,
        default=50,
        help="Maximum comments to fetch per video.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore the 24-hour block and fetch anyway.",
    )

    parser.add_argument(
        "--seed-vodafone-ireland",
        action="store_true",
        help="Add demo Vodafone Ireland YouTube query rules first.",
    )

    args = parser.parse_args()

    if args.seed_vodafone_ireland:
        seed_vodafone_ireland_youtube_rules(args.company_id)
        print("Seeded Vodafone Ireland YouTube query rules.")

    result = collect_youtube_for_company(
        company_id=args.company_id,
        max_videos_per_rule=args.videos,
        max_comments_per_video=args.comments,
        force=args.force,
    )

    print_summary(result)