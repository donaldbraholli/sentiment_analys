import sqlite3
from datetime import datetime
from pathlib import Path


DB_PATH = Path("customer_sentiment.db")


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reddit_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            company_id INTEGER NOT NULL,

            -- Reddit identity
            reddit_id TEXT NOT NULL,
            topic_id TEXT NOT NULL,
            parent_comment_id TEXT,

            -- topic or comment
            entry_type TEXT NOT NULL CHECK(entry_type IN ('topic', 'comment')),

            -- Reddit metadata
            subreddit TEXT,
            title TEXT,
            body TEXT,
            permalink TEXT,
            url TEXT,

            -- privacy-safe user identity
            author_hash TEXT,

            -- engagement/context
            score INTEGER DEFAULT 0,
            num_comments INTEGER DEFAULT 0,

            -- timing
            reddit_created_utc TEXT,
            collected_at TEXT NOT NULL,
            updated_at TEXT,

            -- analysis flags
            is_relevant INTEGER DEFAULT 1,
            service_category TEXT,
            sentiment TEXT,
            sentiment_score REAL,
            analysis_summary TEXT,

            -- raw source label
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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS brands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_name TEXT NOT NULL,
            market_name TEXT,
            country_code TEXT,
            canonical_domain TEXT,
            homepage_url TEXT,
            description TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS brand_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id INTEGER NOT NULL,
            alias TEXT NOT NULL,
            alias_type TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id INTEGER NOT NULL,
            service_name TEXT NOT NULL,
            category TEXT,
            description TEXT,
            keywords TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS public_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_name TEXT,
            source_url TEXT NOT NULL,
            confidence_score REAL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id INTEGER NOT NULL,
            service_id INTEGER,
            source_type TEXT,
            source_url TEXT,
            author TEXT,
            text TEXT NOT NULL,
            sentiment TEXT,
            sentiment_score REAL,
            confidence_score REAL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (brand_id) REFERENCES brands(id),
            FOREIGN KEY (service_id) REFERENCES services(id)
        )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS brand_themes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        brand_id INTEGER NOT NULL,
        primary_color TEXT,
        secondary_color TEXT,
        background_color TEXT,
        text_color TEXT,
        accent_color TEXT,
        logo_url TEXT,
        theme_source TEXT,
        confidence_score REAL DEFAULT 0,
        is_approved INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (brand_id) REFERENCES brands(id)
        )
    """)

    conn.commit()
    conn.close()

def create_comment_analysis_table():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS comment_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            source TEXT NOT NULL,
            source_comment_id TEXT NOT NULL,

            company_id INTEGER,

            brand_relevance TEXT NOT NULL,
            include_in_dashboard INTEGER NOT NULL DEFAULT 1,

            sentiment TEXT,
            sentiment_score REAL,
            confidence TEXT,

            category TEXT,
            subcategory TEXT,
            comment_type TEXT,
            urgency TEXT,

            short_reason TEXT,
            action_hint TEXT,

            model_used TEXT,
            analysis_version TEXT NOT NULL DEFAULT 'v1',

            analyzed_at TEXT NOT NULL,

            UNIQUE(source, source_comment_id, analysis_version)
        )
    """)

    conn.commit()
    conn.close()

SENTIMENT_CATEGORIES = [
    "Network quality",
    "Mobile app",
    "Broadband / home internet",
    "Roaming",
    "Billing / charges",
    "Top-up / prepaid",
    "Customer support",
    "Store experience",
    "Pricing / offers",
    "Data usage / allowance",
    "SIM / eSIM",
    "Device / handset",
    "Account login",
    "Complaint / cancellation",
    "Marketing / advert",
    "Competitor comparison",
    "Praise",
    "Irrelevant / spam",
    "Other",
]


def create_brand(brand_name, market_name=None, country_code=None, canonical_domain=None, homepage_url=None, description=None):
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO brands (
            brand_name,
            market_name,
            country_code,
            canonical_domain,
            homepage_url,
            description,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        brand_name,
        market_name,
        country_code,
        canonical_domain,
        homepage_url,
        description,
        now,
        now
    ))

    brand_id = cur.lastrowid
    conn.commit()
    conn.close()

    return brand_id


def add_brand_alias(brand_id, alias, alias_type="general"):
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO brand_aliases (
            brand_id,
            alias,
            alias_type,
            created_at
        )
        VALUES (?, ?, ?, ?)
    """, (brand_id, alias, alias_type, now))

    conn.commit()
    conn.close()


def add_service(brand_id, service_name, category=None, description=None, keywords=None):
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO services (
            brand_id,
            service_name,
            category,
            description,
            keywords,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        brand_id,
        service_name,
        category,
        description,
        keywords,
        now,
        now
    ))

    conn.commit()
    conn.close()


def get_brands():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, brand_name, market_name, country_code, canonical_domain, homepage_url
        FROM brands
        ORDER BY created_at DESC
    """)

    rows = cur.fetchall()
    conn.close()

    return rows


def get_services_for_brand(brand_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, service_name, category, description, keywords
        FROM services
        WHERE brand_id = ?
        ORDER BY service_name ASC
    """, (brand_id,))

    rows = cur.fetchall()
    conn.close()

    return rows

def update_brand(
    brand_id,
    brand_name,
    market_name=None,
    country_code=None,
    canonical_domain=None,
    homepage_url=None,
    description=None
):
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE brands
        SET
            brand_name = ?,
            market_name = ?,
            country_code = ?,
            canonical_domain = ?,
            homepage_url = ?,
            description = ?,
            updated_at = ?
        WHERE id = ?
    """, (
        brand_name,
        market_name,
        country_code,
        canonical_domain,
        homepage_url,
        description,
        now,
        brand_id
    ))

    conn.commit()
    conn.close()


def delete_brand(brand_id):
    """
    Deletes a brand and related records.
    Be careful: this also removes services, aliases, sources, and mentions.
    """

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM mentions WHERE brand_id = ?", (brand_id,))
    cur.execute("DELETE FROM public_sources WHERE brand_id = ?", (brand_id,))
    cur.execute("DELETE FROM services WHERE brand_id = ?", (brand_id,))
    cur.execute("DELETE FROM brand_aliases WHERE brand_id = ?", (brand_id,))
    cur.execute("DELETE FROM brands WHERE id = ?", (brand_id,))

    conn.commit()
    conn.close()


def get_brand_by_id(brand_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            brand_name,
            market_name,
            country_code,
            canonical_domain,
            homepage_url,
            description
        FROM brands
        WHERE id = ?
    """, (brand_id,))

    row = cur.fetchone()
    conn.close()

    return row


def update_service(
    service_id,
    service_name,
    category=None,
    description=None,
    keywords=None
):
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE services
        SET
            service_name = ?,
            category = ?,
            description = ?,
            keywords = ?,
            updated_at = ?
        WHERE id = ?
    """, (
        service_name,
        category,
        description,
        keywords,
        now,
        service_id
    ))

    conn.commit()
    conn.close()


def delete_service(service_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE mentions
        SET service_id = NULL
        WHERE service_id = ?
    """, (service_id,))

    cur.execute("DELETE FROM services WHERE id = ?", (service_id,))

    conn.commit()
    conn.close()


def get_service_by_id(service_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            brand_id,
            service_name,
            category,
            description,
            keywords
        FROM services
        WHERE id = ?
    """, (service_id,))

    row = cur.fetchone()
    conn.close()

    return row


def get_aliases_for_brand(brand_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            alias,
            alias_type,
            created_at
        FROM brand_aliases
        WHERE brand_id = ?
        ORDER BY alias ASC
    """, (brand_id,))

    rows = cur.fetchall()
    conn.close()

    return rows


def update_brand_alias(alias_id, alias, alias_type=None):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE brand_aliases
        SET
            alias = ?,
            alias_type = ?
        WHERE id = ?
    """, (
        alias,
        alias_type,
        alias_id
    ))

    conn.commit()
    conn.close()


def delete_brand_alias(alias_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM brand_aliases WHERE id = ?", (alias_id,))

    conn.commit()
    conn.close()


def add_public_source(
    brand_id,
    source_type,
    source_name,
    source_url,
    confidence_score=0
):
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO public_sources (
            brand_id,
            source_type,
            source_name,
            source_url,
            confidence_score,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        brand_id,
        source_type,
        source_name,
        source_url,
        confidence_score,
        now
    ))

    conn.commit()
    conn.close()


def get_public_sources_for_brand(brand_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            source_type,
            source_name,
            source_url,
            confidence_score,
            created_at
        FROM public_sources
        WHERE brand_id = ?
        ORDER BY source_type ASC, source_name ASC
    """, (brand_id,))

    rows = cur.fetchall()
    conn.close()

    return rows


def update_public_source(
    source_id,
    source_type,
    source_name,
    source_url,
    confidence_score=0
):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE public_sources
        SET
            source_type = ?,
            source_name = ?,
            source_url = ?,
            confidence_score = ?
        WHERE id = ?
    """, (
        source_type,
        source_name,
        source_url,
        confidence_score,
        source_id
    ))

    conn.commit()
    conn.close()


def delete_public_source(source_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("DELETE FROM public_sources WHERE id = ?", (source_id,))

    conn.commit()
    conn.close()

def add_mention(
    brand_id,
    service_id,
    source_type,
    source_url,
    author,
    text,
    sentiment,
    sentiment_score,
    confidence_score
):
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO mentions (
            brand_id,
            service_id,
            source_type,
            source_url,
            author,
            text,
            sentiment,
            sentiment_score,
            confidence_score,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        brand_id,
        service_id,
        source_type,
        source_url,
        author,
        text,
        sentiment,
        sentiment_score,
        confidence_score,
        now
    ))

    conn.commit()
    conn.close()


def get_mentions_for_brand(brand_id, limit=50):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            mentions.id,
            mentions.text,
            mentions.sentiment,
            mentions.sentiment_score,
            mentions.confidence_score,
            mentions.source_type,
            mentions.source_url,
            mentions.author,
            mentions.created_at,
            services.service_name
        FROM mentions
        LEFT JOIN services
            ON mentions.service_id = services.id
        WHERE mentions.brand_id = ?
        ORDER BY mentions.created_at DESC
        LIMIT ?
    """, (brand_id, limit))

    rows = cur.fetchall()
    conn.close()

    return rows


def get_sentiment_summary_for_brand(brand_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COALESCE(services.service_name, 'Unclassified') AS service_name,
            mentions.sentiment,
            COUNT(*) AS mention_count
        FROM mentions
        LEFT JOIN services
            ON mentions.service_id = services.id
        WHERE mentions.brand_id = ?
        GROUP BY service_name, mentions.sentiment
        ORDER BY service_name ASC, mention_count DESC
    """, (brand_id,))

    rows = cur.fetchall()
    conn.close()

    return rows

def get_total_mentions_count_for_brand(brand_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*)
        FROM mentions
        WHERE brand_id = ?
    """, (brand_id,))

    count = cur.fetchone()[0]
    conn.close()

    return count


def get_overall_sentiment_counts_for_brand(brand_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            sentiment,
            COUNT(*) AS mention_count
        FROM mentions
        WHERE brand_id = ?
        GROUP BY sentiment
        ORDER BY mention_count DESC
    """, (brand_id,))

    rows = cur.fetchall()
    conn.close()

    return rows


def get_service_sentiment_breakdown_for_brand(brand_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COALESCE(services.service_name, 'Unclassified') AS service_name,
            mentions.sentiment,
            COUNT(*) AS mention_count
        FROM mentions
        LEFT JOIN services
            ON mentions.service_id = services.id
        WHERE mentions.brand_id = ?
        GROUP BY service_name, mentions.sentiment
        ORDER BY service_name ASC, mentions.sentiment ASC
    """, (brand_id,))

    rows = cur.fetchall()
    conn.close()

    return rows


def get_negative_mentions_by_service_for_brand(brand_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COALESCE(services.service_name, 'Unclassified') AS service_name,
            COUNT(*) AS negative_count
        FROM mentions
        LEFT JOIN services
            ON mentions.service_id = services.id
        WHERE mentions.brand_id = ?
        AND mentions.sentiment = 'Negative'
        GROUP BY service_name
        ORDER BY negative_count DESC
    """, (brand_id,))

    rows = cur.fetchall()
    conn.close()

    return rows


def get_source_breakdown_for_brand(brand_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            COALESCE(source_type, 'unknown') AS source_type,
            COUNT(*) AS mention_count
        FROM mentions
        WHERE brand_id = ?
        GROUP BY source_type
        ORDER BY mention_count DESC
    """, (brand_id,))

    rows = cur.fetchall()
    conn.close()

    return rows


def get_recent_negative_mentions_for_brand(brand_id, limit=10):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            mentions.text,
            mentions.sentiment,
            mentions.sentiment_score,
            mentions.confidence_score,
            mentions.source_type,
            mentions.source_url,
            mentions.author,
            mentions.created_at,
            COALESCE(services.service_name, 'Unclassified') AS service_name
        FROM mentions
        LEFT JOIN services
            ON mentions.service_id = services.id
        WHERE mentions.brand_id = ?
        AND mentions.sentiment = 'Negative'
        ORDER BY mentions.created_at DESC
        LIMIT ?
    """, (brand_id, limit))

    rows = cur.fetchall()
    conn.close()

    return rows

def get_theme_for_brand(brand_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            brand_id,
            primary_color,
            secondary_color,
            background_color,
            text_color,
            accent_color,
            logo_url,
            theme_source,
            confidence_score,
            is_approved
        FROM brand_themes
        WHERE brand_id = ?
        ORDER BY is_approved DESC, updated_at DESC
        LIMIT 1
    """, (brand_id,))

    row = cur.fetchone()
    conn.close()

    return row


def save_or_update_theme(
    brand_id,
    primary_color,
    secondary_color,
    background_color,
    text_color,
    accent_color,
    logo_url=None,
    theme_source="manual",
    confidence_score=1.0,
    is_approved=1
):
    now = datetime.now().isoformat(timespec="seconds")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT id
        FROM brand_themes
        WHERE brand_id = ?
        LIMIT 1
    """, (brand_id,))

    existing = cur.fetchone()

    if existing:
        theme_id = existing[0]

        cur.execute("""
            UPDATE brand_themes
            SET
                primary_color = ?,
                secondary_color = ?,
                background_color = ?,
                text_color = ?,
                accent_color = ?,
                logo_url = ?,
                theme_source = ?,
                confidence_score = ?,
                is_approved = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            primary_color,
            secondary_color,
            background_color,
            text_color,
            accent_color,
            logo_url,
            theme_source,
            confidence_score,
            is_approved,
            now,
            theme_id
        ))
    else:
        cur.execute("""
            INSERT INTO brand_themes (
                brand_id,
                primary_color,
                secondary_color,
                background_color,
                text_color,
                accent_color,
                logo_url,
                theme_source,
                confidence_score,
                is_approved,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            brand_id,
            primary_color,
            secondary_color,
            background_color,
            text_color,
            accent_color,
            logo_url,
            theme_source,
            confidence_score,
            is_approved,
            now,
            now
        ))

    conn.commit()
    conn.close()