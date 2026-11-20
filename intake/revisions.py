import sqlite3
from dataclasses import dataclass

from intake.row_binding import BoundReading
from protocol.quantities import format_rational, lookup_id, parse_rational


@dataclass(frozen=True)
class ReadingRevision:
    revision_id: int
    round_id: str
    bench_id: str
    parent_id: int | None
    rows: tuple[BoundReading, ...]


def initialize_revision_store(db: sqlite3.Connection) -> None:
    db.executescript('''
        CREATE TABLE IF NOT EXISTS reading_revisions (
            revision_id INTEGER PRIMARY KEY,
            round_id TEXT NOT NULL REFERENCES rounds(round_id),
            bench_id TEXT NOT NULL,
            parent_id INTEGER REFERENCES reading_revisions(revision_id)
        );
        CREATE TABLE IF NOT EXISTS reading_rows (
            revision_id INTEGER NOT NULL REFERENCES reading_revisions(revision_id),
            position INTEGER NOT NULL CHECK (position >= 0),
            row_name TEXT NOT NULL,
            reading TEXT NOT NULL,
            PRIMARY KEY (revision_id, position),
            UNIQUE (revision_id, row_name)
        );
    ''')


def save_revision(db: sqlite3.Connection, round_id: str, bench_id: str,
                  parent_id: int | None, rows: tuple[BoundReading, ...]) -> int:
    db.execute('BEGIN IMMEDIATE')
    with db:
        cursor = db.execute('''
            INSERT INTO reading_revisions (round_id, bench_id, parent_id) VALUES (?, ?, ?)
        ''', (round_id, bench_id, parent_id))
        revision_id = cursor.lastrowid
        db.executemany('''
            INSERT INTO reading_rows (revision_id, position, row_name, reading) VALUES (?, ?, ?, ?)
        ''', ((revision_id, row.position, row.row_name, format_rational(row.value)) for row in rows))
    return revision_id


def get_revision(db: sqlite3.Connection, revision_id: int) -> ReadingRevision:
    lookup_id(revision_id)
    header = db.execute('''
        SELECT round_id, bench_id, parent_id FROM reading_revisions WHERE revision_id = ?
    ''', (revision_id,)).fetchone()
    if header is None:
        raise KeyError(revision_id)
    round_id, bench_id, parent_id = header
    result = db.execute('''
        SELECT row_name, position, reading FROM reading_rows
        WHERE revision_id = ? ORDER BY position
    ''', (revision_id,))
    rows = tuple(BoundReading(name, position, parse_rational(value)) for name, position, value in result)
    return ReadingRevision(revision_id, round_id, bench_id, parent_id, rows)
