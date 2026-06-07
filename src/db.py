"""SQLite tracking for item pipeline status."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "items.db"

VALID_STATUSES = {"drafted", "priced", "created", "published", "sold"}


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS items (
                item_id      TEXT PRIMARY KEY,
                status       TEXT NOT NULL DEFAULT 'drafted',
                draft_path   TEXT,
                offer_id     TEXT,
                listing_id   TEXT,
                updated_at   TEXT DEFAULT (datetime('now'))
            )
        """)


def upsert_item(
    item_id: str,
    status: str,
    draft_path: str | None = None,
    offer_id: str | None = None,
    listing_id: str | None = None,
) -> None:
    assert status in VALID_STATUSES, f"Invalid status: {status}"
    with _conn() as con:
        con.execute("""
            INSERT INTO items (item_id, status, draft_path, offer_id, listing_id, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(item_id) DO UPDATE SET
                status     = excluded.status,
                draft_path = COALESCE(excluded.draft_path, draft_path),
                offer_id   = COALESCE(excluded.offer_id, offer_id),
                listing_id = COALESCE(excluded.listing_id, listing_id),
                updated_at = excluded.updated_at
        """, (item_id, status, draft_path, offer_id, listing_id))


def get_item(item_id: str) -> sqlite3.Row | None:
    with _conn() as con:
        return con.execute("SELECT * FROM items WHERE item_id = ?", (item_id,)).fetchone()


def list_items() -> list[sqlite3.Row]:
    with _conn() as con:
        return con.execute("SELECT * FROM items ORDER BY item_id").fetchall()
