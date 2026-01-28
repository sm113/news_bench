"""
News Bench - Database Module
============================
SQLite storage for articles and synthesized stories.
Supports both local SQLite and Turso (hosted SQLite) for production.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from contextlib import contextmanager

# =============================================================================
# DATABASE CONFIG
# =============================================================================
from config import DATABASE_PATH

# Turso configuration (set these env vars for production)
TURSO_DATABASE_URL = os.environ.get('TURSO_DATABASE_URL')
TURSO_AUTH_TOKEN = os.environ.get('TURSO_AUTH_TOKEN')

# Use Turso if configured, otherwise local SQLite
USE_TURSO = bool(TURSO_DATABASE_URL and TURSO_AUTH_TOKEN)

_libsql = None
if USE_TURSO:
    try:
        import libsql_experimental as _libsql
        print(f"[DATABASE] Using Turso: {TURSO_DATABASE_URL[:50]}...")
    except ImportError:
        print("[DATABASE] WARNING: libsql_experimental not installed, falling back to local SQLite")
        USE_TURSO = False

if not USE_TURSO:
    print(f"[DATABASE] Using local SQLite: {DATABASE_PATH}")


# =============================================================================
# CONNECTION MANAGEMENT
# =============================================================================

def _get_raw_connection():
    """Get a raw database connection."""
    if USE_TURSO:
        return _libsql.connect(database=TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)
    else:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


def _row_to_dict(cursor, row):
    """Convert a row to a dictionary using cursor description."""
    if row is None:
        return None
    if hasattr(row, 'keys'):
        return dict(row)
    columns = [col[0] for col in cursor.description]
    return dict(zip(columns, row))


def _fetchall_dicts(cursor):
    """Fetch all rows as dictionaries."""
    rows = cursor.fetchall()
    return [_row_to_dict(cursor, row) for row in rows]


def _fetchone_dict(cursor):
    """Fetch one row as dictionary."""
    row = cursor.fetchone()
    return _row_to_dict(cursor, row) if row else None


@contextmanager
def get_connection():
    """Context manager for database connections with proper commit/rollback."""
    conn = _get_raw_connection()
    if not USE_TURSO:
        conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception as e:
        try:
            conn.rollback()
        except:
            pass
        raise
    finally:
        try:
            conn.close()
        except:
            pass


# =============================================================================
# DATABASE INITIALIZATION
# =============================================================================

_initialized = False

def init_database():
    """Initialize the database with required tables."""
    global _initialized
    if _initialized:
        return
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL,
                source_lean TEXT NOT NULL,
                headline TEXT NOT NULL,
                lede TEXT,
                url TEXT UNIQUE NOT NULL,
                published_at TEXT,
                created_at TEXT NOT NULL,
                embedding BLOB
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                synthesized_headline TEXT NOT NULL,
                consensus TEXT,
                left_framing TEXT,
                right_framing TEXT,
                center_framing TEXT,
                key_differences TEXT,
                source_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS story_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                story_id INTEGER NOT NULL,
                article_id INTEGER NOT NULL,
                FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE CASCADE,
                FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
                UNIQUE(story_id, article_id)
            )
        """)

        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_created ON articles(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stories_created ON stories(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_story_sources_story ON story_sources(story_id)")

    _initialized = True
    print("[DATABASE] Initialized successfully")


# =============================================================================
# ARTICLE OPERATIONS
# =============================================================================

def insert_article(
    source_name: str,
    source_lean: str,
    headline: str,
    lede: str,
    url: str,
    published_at: str = None
) -> Optional[int]:
    """Insert a new article. Returns article ID or None if duplicate."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO articles (source_name, source_lean, headline, lede, url, published_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (source_name, source_lean, headline, lede, url, published_at, datetime.now().isoformat()))
            return cursor.lastrowid
    except Exception as e:
        error_str = str(e).lower()
        if 'unique' in error_str or 'constraint' in error_str:
            return None  # Duplicate URL, this is expected
        print(f"[DATABASE] Error inserting article: {e}")
        return None


def get_recent_articles(hours: int = 48) -> List[Dict]:
    """Get articles from the last N hours."""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, source_name, source_lean, headline, lede, url, published_at, created_at
            FROM articles WHERE created_at > ? ORDER BY created_at DESC
        """, (cutoff,))
        return _fetchall_dicts(cursor)


def get_articles_without_embedding(limit: int = 100) -> List[Dict]:
    """Get articles that don't have embeddings yet."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, source_name, source_lean, headline, lede, url, published_at, created_at
            FROM articles WHERE embedding IS NULL ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        return _fetchall_dicts(cursor)


def update_article_embedding(article_id: int, embedding: bytes):
    """Store embedding for an article."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE articles SET embedding = ? WHERE id = ?", (embedding, article_id))


def get_articles_with_embeddings(hours: int = 48) -> List[Dict]:
    """Get articles with embeddings from the last N hours."""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, source_name, source_lean, headline, lede, url, published_at, created_at, embedding
            FROM articles WHERE created_at > ? AND embedding IS NOT NULL ORDER BY created_at DESC
        """, (cutoff,))
        return _fetchall_dicts(cursor)


def get_article_by_id(article_id: int) -> Optional[Dict]:
    """Get a single article by ID."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, source_name, source_lean, headline, lede, url, published_at, created_at
            FROM articles WHERE id = ?
        """, (article_id,))
        return _fetchone_dict(cursor)


def get_unclustered_article_ids(hours: int = 48) -> List[int]:
    """Get IDs of articles not yet assigned to any story."""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.id FROM articles a
            LEFT JOIN story_sources ss ON a.id = ss.article_id
            WHERE a.created_at > ? AND ss.id IS NULL AND a.embedding IS NOT NULL
        """, (cutoff,))
        return [row[0] for row in cursor.fetchall()]


# =============================================================================
# STORY OPERATIONS
# =============================================================================

def insert_story(
    synthesized_headline: str,
    consensus: str,
    left_framing: str,
    right_framing: str,
    center_framing: str,
    key_differences: str,
    article_ids: List[int]
) -> Optional[int]:
    """Insert a new synthesized story with its source articles."""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            cursor.execute("""
                INSERT INTO stories (synthesized_headline, consensus, left_framing, right_framing,
                                     center_framing, key_differences, source_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (synthesized_headline, consensus, left_framing, right_framing,
                  center_framing, key_differences, len(article_ids), now, now))

            story_id = cursor.lastrowid

            for article_id in article_ids:
                cursor.execute(
                    "INSERT OR IGNORE INTO story_sources (story_id, article_id) VALUES (?, ?)",
                    (story_id, article_id)
                )

            return story_id
    except Exception as e:
        print(f"[DATABASE] Error inserting story: {e}")
        return None


def get_stories(limit: int = 20, offset: int = 0) -> List[Dict]:
    """Get synthesized stories sorted by recency."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, synthesized_headline, consensus, left_framing, right_framing,
                   center_framing, key_differences, source_count, created_at, updated_at
            FROM stories ORDER BY created_at DESC LIMIT ? OFFSET ?
        """, (limit, offset))
        return _fetchall_dicts(cursor)


def get_story_with_sources(story_id: int) -> Optional[Dict]:
    """Get a story with all its source articles."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, synthesized_headline, consensus, left_framing, right_framing,
                   center_framing, key_differences, source_count, created_at, updated_at
            FROM stories WHERE id = ?
        """, (story_id,))
        story = _fetchone_dict(cursor)
        if not story:
            return None

        cursor.execute("""
            SELECT a.id, a.source_name, a.source_lean, a.headline, a.lede, a.url, a.published_at
            FROM articles a
            JOIN story_sources ss ON a.id = ss.article_id
            WHERE ss.story_id = ?
            ORDER BY a.source_lean, a.source_name
        """, (story_id,))
        story['sources'] = _fetchall_dicts(cursor)
        return story


def get_stories_count() -> int:
    """Get total number of stories."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM stories")
        return cursor.fetchone()[0]


def get_sources_for_story(story_id: int) -> List[Dict]:
    """Get all source articles for a story."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.id, a.source_name, a.source_lean, a.headline, a.lede, a.url, a.published_at
            FROM articles a
            JOIN story_sources ss ON a.id = ss.article_id
            WHERE ss.story_id = ?
            ORDER BY a.source_lean, a.source_name
        """, (story_id,))
        return _fetchall_dicts(cursor)


# =============================================================================
# STATS AND MAINTENANCE
# =============================================================================

def get_stats() -> Dict:
    """Get database statistics."""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM articles")
        total_articles = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM stories")
        total_stories = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT source_name) FROM articles")
        unique_sources = cursor.fetchone()[0]

        cursor.execute("SELECT MAX(created_at) FROM articles")
        last_article = cursor.fetchone()[0]

        cursor.execute("SELECT MAX(created_at) FROM stories")
        last_story = cursor.fetchone()[0]

        return {
            'total_articles': total_articles,
            'total_stories': total_stories,
            'unique_sources': unique_sources,
            'last_article_at': last_article,
            'last_story_at': last_story
        }


def cleanup_old_data(days: int = 7):
    """Remove articles and stories older than N days."""
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM stories WHERE created_at < ?", (cutoff,))
        cursor.execute("""
            DELETE FROM articles
            WHERE created_at < ? AND id NOT IN (SELECT article_id FROM story_sources)
        """, (cutoff,))
    print(f"[DATABASE] Cleaned up data older than {days} days")


if __name__ == "__main__":
    init_database()
    print(get_stats())
