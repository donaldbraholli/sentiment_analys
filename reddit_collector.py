from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import praw
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


@dataclass
class RedditFetchSummary:
    company_id: int
    status: str
    topics_found: int = 0
    comments_found: int = 0
    entries_inserted: int = 0
    entries_updated: int = 0
    skipped_reason: str | None = None
    error_message: str | None = None


# ------------------------------------------------------------
# Utility helpers
# ------------------------------------------------------------

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def reddit_timestamp_to_iso(created_utc: float | int | None) -> str | None:
    if created_utc is None:
        return None

    return datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat(timespec="seconds")


def parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def hash_reddit_author(author_name: str | None) -> str | None:
    """
    Stores a stable hash instead of the real Reddit username.

    Same username + same salt = same hash.
    Different salt = different hashes.
    """
    if not author_name:
        return None

    author_name = str(author_name).strip()

    if not author_name or author_name.lower() in {"[deleted]", "deleted"}:
        return None

    salt = os.getenv("AUTHOR_HASH_SALT", "customer_sentiment_default_salt")
    raw = f"{salt}:{author_name}".encode("utf-8")

    return hashlib.sha256(raw).hexdigest()


def normalize_parent_comment_id(parent_id: str | None) -> str | None:
    """
    Reddit parent IDs look like:
    - t3_abc123 = parent is the topic/submission
    - t1_xyz789 = parent is another comment

    We only store parent_comment_id when the parent is another comment.
    """
    if not parent_id:
        return None

    if parent_id.startswith("t1_"):
        return parent_id.replace("t1_", "", 1)

    return None


def safe_text(value: str | None) -> str | None:
    if value is None:
        return None

    value = str(value)

    if value.strip().lower() in {"[deleted]", "[removed]"}:
        return None

    return value


# ------------------------------------------------------------
# Database
# ------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_reddit_tables(conn: sqlite3.Connection) -> None:
    """
    Safe to run every time.
    If the tables already exist, nothing happens.
    """
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reddit_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        company_id INTEGER NOT NULL,

        reddit_id TEXT NOT NULL,
        topic_id TEXT NOT NULL,
        parent_comment_id TEXT,

        entry_type TEXT NOT NULL CHECK(entry_type IN ('topic', 'comment')),

        subreddit TEXT,
        title TEXT,
        body TEXT,
        permalink TEXT,
        url TEXT,

        author_hash TEXT,

        score INTEGER DEFAULT 0,
        num_comments INTEGER DEFAULT 0,

        reddit_created_utc TEXT,
        collected_at TEXT NOT NULL,
        updated_at TEXT,

        is_relevant INTEGER DEFAULT 1,
        service_category TEXT,
        sentiment TEXT,
        sentiment_score REAL,
        analysis_summary TEXT,

        source TEXT DEFAULT 'reddit',

        UNIQUE(company_id, reddit_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reddit_fetch_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        company_id INTEGER NOT NULL,

        started_at TEXT NOT NULL,
        finished_at TEXT,

        status TEXT NOT NULL,
        error_message TEXT,

        topics_found INTEGER DEFAULT 0,
        comments_found INTEGER DEFAULT 0,
        entries_inserted INTEGER DEFAULT 0,
        entries_updated INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS reddit_query_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,

        company_id INTEGER NOT NULL,

        query TEXT NOT NULL,
        subreddit TEXT,
        enabled INTEGER DEFAULT 1,

        created_at TEXT NOT NULL,

        UNIQUE(company_id, query, subreddit)
    )
    """)

    conn.commit()


def entry_exists(conn: sqlite3.Connection, company_id: int, reddit_id: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1
        FROM reddit_entries
        WHERE company_id = ?
          AND reddit_id = ?
        LIMIT 1
        """,
        (company_id, reddit_id),
    )

    return cur.fetchone() is not None


def upsert_reddit_entry(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    reddit_id: str,
    topic_id: str,
    parent_comment_id: str | None,
    entry_type: str,
    subreddit: str | None,
    title: str | None,
    body: str | None,
    permalink: str | None,
    url: str | None,
    author_hash: str | None,
    score: int,
    num_comments: int,
    reddit_created_utc: str | None,
) -> str:
    """
    Returns:
    - "inserted"
    - "updated"
    """
    existed_before = entry_exists(conn, company_id, reddit_id)

    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO reddit_entries (
            company_id,
            reddit_id,
            topic_id,
            parent_comment_id,
            entry_type,
            subreddit,
            title,
            body,
            permalink,
            url,
            author_hash,
            score,
            num_comments,
            reddit_created_utc,
            collected_at,
            updated_at,
            source
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'reddit')
        ON CONFLICT(company_id, reddit_id)
        DO UPDATE SET
            topic_id = excluded.topic_id,
            parent_comment_id = excluded.parent_comment_id,
            entry_type = excluded.entry_type,
            subreddit = excluded.subreddit,
            title = excluded.title,
            body = excluded.body,
            permalink = excluded.permalink,
            url = excluded.url,
            author_hash = excluded.author_hash,
            score = excluded.score,
            num_comments = excluded.num_comments,
            reddit_created_utc = excluded.reddit_created_utc,
            updated_at = excluded.updated_at
        """,
        (
            company_id,
            reddit_id,
            topic_id,
            parent_comment_id,
            entry_type,
            subreddit,
            title,
            body,
            permalink,
            url,
            author_hash,
            score,
            num_comments,
            reddit_created_utc,
            now_utc_iso(),
            now_utc_iso(),
        ),
    )

    conn.commit()

    return "updated" if existed_before else "inserted"


def get_enabled_reddit_rules(conn: sqlite3.Connection, company_id: int) -> list[sqlite3.Row]:
    cur = conn.cursor()

    cur.execute(
        """
        SELECT query, subreddit
        FROM reddit_query_rules
        WHERE company_id = ?
          AND enabled = 1
        ORDER BY id ASC
        """,
        (company_id,),
    )

    return cur.fetchall()


def add_reddit_query_rule(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    query: str,
    subreddit: str | None = None,
) -> None:
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO reddit_query_rules (
            company_id,
            query,
            subreddit,
            enabled,
            created_at
        )
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(company_id, query, subreddit)
        DO UPDATE SET
            enabled = 1
        """,
        (
            company_id,
            query,
            subreddit,
            now_utc_iso(),
        ),
    )

    conn.commit()


def get_last_successful_run(conn: sqlite3.Connection, company_id: int) -> sqlite3.Row | None:
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM reddit_fetch_runs
        WHERE company_id = ?
          AND status = 'success'
          AND finished_at IS NOT NULL
        ORDER BY finished_at DESC
        LIMIT 1
        """,
        (company_id,),
    )

    return cur.fetchone()


def can_run_reddit_fetch(
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

    return False, f"Last successful Reddit fetch was less than {min_hours_between_runs} hours ago."


def start_fetch_run(conn: sqlite3.Connection, company_id: int) -> int:
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO reddit_fetch_runs (
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
    topics_found: int = 0,
    comments_found: int = 0,
    entries_inserted: int = 0,
    entries_updated: int = 0,
) -> None:
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE reddit_fetch_runs
        SET
            finished_at = ?,
            status = ?,
            error_message = ?,
            topics_found = ?,
            comments_found = ?,
            entries_inserted = ?,
            entries_updated = ?
        WHERE id = ?
        """,
        (
            now_utc_iso(),
            status,
            error_message,
            topics_found,
            comments_found,
            entries_inserted,
            entries_updated,
            run_id,
        ),
    )

    conn.commit()


# ------------------------------------------------------------
# Reddit client
# ------------------------------------------------------------

def get_reddit_client() -> praw.Reddit:
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT")

    missing = []

    if not client_id:
        missing.append("REDDIT_CLIENT_ID")

    if not client_secret:
        missing.append("REDDIT_CLIENT_SECRET")

    if not user_agent:
        missing.append("REDDIT_USER_AGENT")

    if missing:
        raise RuntimeError(
            "Missing Reddit environment variables: "
            + ", ".join(missing)
            + ". Add them to your .env file."
        )

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
        check_for_async=False,
    )

    reddit.read_only = True

    return reddit


# ------------------------------------------------------------
# Collection logic
# ------------------------------------------------------------

def save_topic(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    submission,
) -> str:
    reddit_id = submission.id
    topic_id = submission.id

    author_hash = hash_reddit_author(str(submission.author) if submission.author else None)

    permalink = f"https://www.reddit.com{submission.permalink}"

    return upsert_reddit_entry(
        conn,
        company_id=company_id,
        reddit_id=reddit_id,
        topic_id=topic_id,
        parent_comment_id=None,
        entry_type="topic",
        subreddit=str(submission.subreddit) if submission.subreddit else None,
        title=safe_text(submission.title),
        body=safe_text(getattr(submission, "selftext", None)),
        permalink=permalink,
        url=getattr(submission, "url", None),
        author_hash=author_hash,
        score=int(getattr(submission, "score", 0) or 0),
        num_comments=int(getattr(submission, "num_comments", 0) or 0),
        reddit_created_utc=reddit_timestamp_to_iso(getattr(submission, "created_utc", None)),
    )


def save_comment(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    submission,
    comment,
) -> str | None:
    body = safe_text(getattr(comment, "body", None))

    if not body:
        return None

    reddit_id = comment.id
    topic_id = submission.id

    author_hash = hash_reddit_author(str(comment.author) if comment.author else None)

    permalink = f"https://www.reddit.com{comment.permalink}"

    parent_comment_id = normalize_parent_comment_id(getattr(comment, "parent_id", None))

    return upsert_reddit_entry(
        conn,
        company_id=company_id,
        reddit_id=reddit_id,
        topic_id=topic_id,
        parent_comment_id=parent_comment_id,
        entry_type="comment",
        subreddit=str(submission.subreddit) if submission.subreddit else None,
        title=None,
        body=body,
        permalink=permalink,
        url=None,
        author_hash=author_hash,
        score=int(getattr(comment, "score", 0) or 0),
        num_comments=0,
        reddit_created_utc=reddit_timestamp_to_iso(getattr(comment, "created_utc", None)),
    )


def collect_comments_for_submission(
    conn: sqlite3.Connection,
    *,
    company_id: int,
    submission,
    max_comments_per_topic: int,
) -> tuple[int, int, int]:
    """
    Returns:
    comments_found, entries_inserted, entries_updated
    """
    comments_found = 0
    entries_inserted = 0
    entries_updated = 0

    submission.comment_sort = "new"
    submission.comment_limit = max_comments_per_topic

    submission.comments.replace_more(limit=0)

    comments = submission.comments.list()

    for comment in comments[:max_comments_per_topic]:
        result = save_comment(
            conn,
            company_id=company_id,
            submission=submission,
            comment=comment,
        )

        if result is None:
            continue

        comments_found += 1

        if result == "inserted":
            entries_inserted += 1
        elif result == "updated":
            entries_updated += 1

    return comments_found, entries_inserted, entries_updated


def collect_reddit_for_company(
    company_id: int,
    *,
    max_topics_per_rule: int = 25,
    max_comments_per_topic: int = 50,
    min_hours_between_runs: int | None = None,
    force: bool = False,
) -> RedditFetchSummary:
    """
    Main function.

    This:
    - blocks duplicate runs inside the 24h window unless force=True
    - loads reddit_query_rules for the company
    - searches Reddit
    - saves topics
    - saves comments under each topic
    """
    if min_hours_between_runs is None:
        min_hours_between_runs = int(os.getenv("REDDIT_DAILY_LIMIT_HOURS", "24"))

    conn = get_connection()
    ensure_reddit_tables(conn)

    can_run, skipped_reason = can_run_reddit_fetch(
        conn,
        company_id,
        min_hours_between_runs=min_hours_between_runs,
    )

    if not can_run and not force:
        conn.close()

        return RedditFetchSummary(
            company_id=company_id,
            status="skipped",
            skipped_reason=skipped_reason,
        )

    rules = get_enabled_reddit_rules(conn, company_id)

    if not rules:
        conn.close()

        return RedditFetchSummary(
            company_id=company_id,
            status="skipped",
            skipped_reason="No enabled Reddit query rules found for this company.",
        )

    run_id = start_fetch_run(conn, company_id)

    summary = RedditFetchSummary(
        company_id=company_id,
        status="running",
    )

    try:
        reddit = get_reddit_client()

        for rule in rules:
            query = rule["query"]
            subreddit_name = rule["subreddit"] or "all"

            subreddit = reddit.subreddit(subreddit_name)

            for submission in subreddit.search(
                query,
                sort="new",
                time_filter="week",
                limit=max_topics_per_rule,
            ):
                topic_result = save_topic(
                    conn,
                    company_id=company_id,
                    submission=submission,
                )

                summary.topics_found += 1

                if topic_result == "inserted":
                    summary.entries_inserted += 1
                elif topic_result == "updated":
                    summary.entries_updated += 1

                comments_found, comment_inserts, comment_updates = collect_comments_for_submission(
                    conn,
                    company_id=company_id,
                    submission=submission,
                    max_comments_per_topic=max_comments_per_topic,
                )

                summary.comments_found += comments_found
                summary.entries_inserted += comment_inserts
                summary.entries_updated += comment_updates

        summary.status = "success"

        finish_fetch_run(
            conn,
            run_id=run_id,
            status="success",
            topics_found=summary.topics_found,
            comments_found=summary.comments_found,
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
            topics_found=summary.topics_found,
            comments_found=summary.comments_found,
            entries_inserted=summary.entries_inserted,
            entries_updated=summary.entries_updated,
        )

    finally:
        conn.close()

    return summary


# ------------------------------------------------------------
# Optional: quick test helpers
# ------------------------------------------------------------

def seed_vodafone_ireland_reddit_rules(company_id: int) -> None:
    """
    Temporary helper for your Vodafone Ireland demo.
    Later we should move this into the Register Brand / Admin screen.
    """
    conn = get_connection()
    ensure_reddit_tables(conn)

    rules = [
        ("Vodafone Ireland", "ireland"),
        ("vodafone.ie", "ireland"),
        ("Vodafone broadband Ireland", "ireland"),
        ("Vodafone mobile Ireland", "ireland"),
        ("Vodafone roaming Ireland", "ireland"),
        ("Vodafone app Ireland", "ireland"),
        ("Vodafone customer service Ireland", "ireland"),
        ("Vodafone 5G Ireland", "ireland"),
        ("Vodafone outage Ireland", "ireland"),
        ("Vodafone", "ireland"),
    ]

    for query, subreddit in rules:
        add_reddit_query_rule(
            conn,
            company_id=company_id,
            query=query,
            subreddit=subreddit,
        )

    conn.close()


def print_summary(summary: RedditFetchSummary) -> None:
    print("")
    print("Reddit fetch summary")
    print("--------------------")
    print(f"Company ID:       {summary.company_id}")
    print(f"Status:           {summary.status}")
    print(f"Topics found:     {summary.topics_found}")
    print(f"Comments found:   {summary.comments_found}")
    print(f"Inserted:         {summary.entries_inserted}")
    print(f"Updated:          {summary.entries_updated}")

    if summary.skipped_reason:
        print(f"Skipped reason:   {summary.skipped_reason}")

    if summary.error_message:
        print(f"Error:            {summary.error_message}")

    print("")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Collect Reddit sentiment data.")

    parser.add_argument(
        "--company-id",
        type=int,
        required=True,
        help="Company ID from your companies table.",
    )

    parser.add_argument(
        "--topics",
        type=int,
        default=25,
        help="Maximum Reddit topics to fetch per query rule.",
    )

    parser.add_argument(
        "--comments",
        type=int,
        default=50,
        help="Maximum comments to fetch per topic.",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore the 24-hour block and fetch anyway.",
    )

    parser.add_argument(
        "--seed-vodafone-ireland",
        action="store_true",
        help="Add demo Vodafone Ireland Reddit query rules first.",
    )

    args = parser.parse_args()

    if args.seed_vodafone_ireland:
        seed_vodafone_ireland_reddit_rules(args.company_id)
        print("Seeded Vodafone Ireland Reddit query rules.")

    result = collect_reddit_for_company(
        company_id=args.company_id,
        max_topics_per_rule=args.topics,
        max_comments_per_topic=args.comments,
        force=args.force,
    )

    print_summary(result)