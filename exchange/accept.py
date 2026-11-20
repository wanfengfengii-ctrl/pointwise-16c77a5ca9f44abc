import sqlite3

from exchange.catalog import find_by_issuer, insert_acceptance
from exchange.codec import decode_summary


def accept_summary(db: sqlite3.Connection, wire: str) -> int:
    summary = decode_summary(wire)
    db.execute('BEGIN IMMEDIATE')
    with db:
        original = find_by_issuer(db, summary.identity)
        if original is None:
            acceptance_id = insert_acceptance(db, summary, wire)
        elif original.summary == summary:
            acceptance_id = original.acceptance_id
        else:
            raise ValueError('conflicting content for an accepted issuer identity')
    return acceptance_id
