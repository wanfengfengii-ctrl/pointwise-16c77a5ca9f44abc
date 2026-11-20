import sqlite3

from exchange.catalog import find_by_issuer, insert_acceptance
from exchange.codec import decode_summary
from exchange.isolation_catalog import (
    find_evidence_by_identity,
    format_acceptance_id,
    insert_evidence,
)
from exchange.isolation_codec import decode_isolation_evidence


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


def accept_isolation_evidence(db: sqlite3.Connection, wire: str) -> str:
    """Accept a V2 evidence body and return its fixed ``v2:N`` id.

    Re-issuing the same evidence (same round, bench and exact revision with an
    equivalent canonical relation) reuses the first acceptance id and keeps
    the first wire.  Conflicting content for that identity is rejected.
    """
    evidence = decode_isolation_evidence(wire)
    db.execute('BEGIN IMMEDIATE')
    with db:
        original = find_evidence_by_identity(db, evidence)
        if original is None:
            sequence = insert_evidence(db, evidence, wire)
        elif original.evidence == evidence:
            sequence = original.acceptance_id
        else:
            raise ValueError('conflicting content for an accepted evidence identity')
    return format_acceptance_id(sequence)
