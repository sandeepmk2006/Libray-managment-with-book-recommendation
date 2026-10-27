"""SQLite storage layer and pandas loaders."""
import os
import sqlite3

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("LIBRARY_DB", os.path.join(ROOT, "data", "library.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    member_id  TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    department TEXT NOT NULL,
    year       INTEGER NOT NULL,          -- 1-4 students, 0 = faculty
    gender     TEXT NOT NULL,             -- used only for fairness audits
    joined     TEXT NOT NULL,
    consent    INTEGER NOT NULL DEFAULT 1 -- 1 = allows personalised recommendations
);
CREATE TABLE IF NOT EXISTS books (
    book_id     INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    author      TEXT NOT NULL,
    genre       TEXT NOT NULL,
    year        INTEGER,
    pages       INTEGER,
    description TEXT,
    copies      INTEGER NOT NULL DEFAULT 3,
    ol_key      TEXT,                     -- Open Library work id (scraped)
    ol_rating   REAL,                     -- Open Library community rating (scraped)
    want_to_read INTEGER                  -- Open Library want-to-read count (scraped)
);
CREATE TABLE IF NOT EXISTS visits (
    visit_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id  TEXT NOT NULL REFERENCES members(member_id),
    entry_time TEXT NOT NULL,             -- ISO 8601
    exit_time  TEXT,                      -- NULL while inside
    purpose    TEXT                       -- may be NULL (missing data on purpose)
);
CREATE TABLE IF NOT EXISTS loans (
    loan_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id TEXT NOT NULL REFERENCES members(member_id),
    book_id   INTEGER NOT NULL REFERENCES books(book_id),
    issued    TEXT NOT NULL,
    due       TEXT NOT NULL,
    returned  TEXT                        -- NULL while on loan
);
CREATE TABLE IF NOT EXISTS ratings (
    member_id TEXT NOT NULL,
    book_id   INTEGER NOT NULL,
    rating    REAL NOT NULL,              -- 1..5
    ts        TEXT NOT NULL,
    PRIMARY KEY (member_id, book_id)
);
CREATE INDEX IF NOT EXISTS ix_visits_member ON visits(member_id);
CREATE INDEX IF NOT EXISTS ix_visits_open ON visits(exit_time);
CREATE INDEX IF NOT EXISTS ix_loans_member ON loans(member_id);
"""


def connect(path=None):
    conn = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def load_frames(conn):
    """Return every table as a pandas DataFrame with parsed datetimes.

    Keys: members, books, visits, loans, ratings.
    visits gets extra column duration_min (NaN while still inside).
    loans gets extra columns days_late (NaN while open) and is_late (bool/NaN).
    """
    q = lambda sql: pd.read_sql_query(sql, conn)
    members = q("SELECT * FROM members")
    books = q("SELECT * FROM books")
    visits = q("SELECT * FROM visits")
    loans = q("SELECT * FROM loans")
    ratings = q("SELECT * FROM ratings")

    members["joined"] = pd.to_datetime(members["joined"])
    for c in ("entry_time", "exit_time"):
        visits[c] = pd.to_datetime(visits[c])
    visits["duration_min"] = (visits["exit_time"] - visits["entry_time"]).dt.total_seconds() / 60
    for c in ("issued", "due", "returned"):
        loans[c] = pd.to_datetime(loans[c])
    loans["days_late"] = (loans["returned"] - loans["due"]).dt.total_seconds() / 86400
    loans["days_late"] = loans["days_late"].clip(lower=0)
    loans["is_late"] = loans["days_late"].gt(0).where(loans["returned"].notna())
    ratings["ts"] = pd.to_datetime(ratings["ts"])
    return {"members": members, "books": books, "visits": visits,
            "loans": loans, "ratings": ratings}
