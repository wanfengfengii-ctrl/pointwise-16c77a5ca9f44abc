import sqlite3
from dataclasses import dataclass

from intake.revisions import ReadingRevision, get_revision
from protocol.quantities import lookup_id


@dataclass(frozen=True)
class FrozenRevision:
    freeze_id: int
    revision: ReadingRevision


def initialize_freeze_store(db: sqlite3.Connection) -> None:
    db.execute('''
        CREATE TABLE IF NOT EXISTS frozen_revisions (
            freeze_id INTEGER PRIMARY KEY,
            revision_id INTEGER NOT NULL REFERENCES reading_revisions(revision_id)
        )
    ''')


def freeze_revision(db: sqlite3.Connection, revision_id: int) -> int:
    revision = get_revision(db, revision_id)
    if not revision.rows:
        raise ValueError('cannot freeze an empty revision')
    db.execute('BEGIN IMMEDIATE')
    with db:
        cursor = db.execute('INSERT INTO frozen_revisions (revision_id) VALUES (?)', (revision.revision_id,))
        freeze_id = cursor.lastrowid
    return freeze_id


def get_frozen_revision(db: sqlite3.Connection, freeze_id: int) -> FrozenRevision:
    lookup_id(freeze_id)
    row = db.execute('SELECT revision_id FROM frozen_revisions WHERE freeze_id = ?', (freeze_id,)).fetchone()
    if row is None:
        raise KeyError(freeze_id)
    return FrozenRevision(freeze_id, get_revision(db, row[0]))
