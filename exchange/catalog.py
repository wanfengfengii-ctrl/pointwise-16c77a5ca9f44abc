import sqlite3
from dataclasses import dataclass

from exchange.codec import decode_summary
from exchange.envelope import IssuerIdentity, V1Summary
from protocol.quantities import lookup_id


@dataclass(frozen=True)
class AcceptedSummary:
    acceptance_id: int
    wire: str
    summary: V1Summary


def initialize_acceptance_store(db: sqlite3.Connection) -> None:
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('''
        CREATE TABLE IF NOT EXISTS accepted_summaries (
            acceptance_id INTEGER PRIMARY KEY,
            issuer_bench TEXT NOT NULL,
            local_report_id INTEGER NOT NULL CHECK (local_report_id > 0),
            wire TEXT NOT NULL,
            UNIQUE (issuer_bench, local_report_id)
        )
    ''')


def _accepted(row) -> AcceptedSummary:
    acceptance_id, wire = row
    return AcceptedSummary(acceptance_id, wire, decode_summary(wire))


def find_by_issuer(db: sqlite3.Connection, identity: IssuerIdentity) -> AcceptedSummary | None:
    row = db.execute('''
        SELECT acceptance_id, wire FROM accepted_summaries
        WHERE issuer_bench = ? AND local_report_id = ?
    ''', (identity.bench_id, identity.local_report_id)).fetchone()
    return None if row is None else _accepted(row)


def insert_acceptance(db: sqlite3.Connection, summary: V1Summary, wire: str) -> int:
    if not db.in_transaction:
        raise RuntimeError('acceptance insert requires the caller transaction')
    cursor = db.execute('''
        INSERT INTO accepted_summaries (issuer_bench, local_report_id, wire) VALUES (?, ?, ?)
    ''', (summary.identity.bench_id, summary.identity.local_report_id, wire))
    return cursor.lastrowid


def get_accepted_summary(db: sqlite3.Connection, acceptance_id: int) -> AcceptedSummary:
    lookup_id(acceptance_id)
    row = db.execute('''
        SELECT acceptance_id, wire FROM accepted_summaries WHERE acceptance_id = ?
    ''', (acceptance_id,)).fetchone()
    if row is None:
        raise KeyError(acceptance_id)
    return _accepted(row)
