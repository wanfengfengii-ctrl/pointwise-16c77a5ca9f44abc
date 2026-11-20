"""Persistence helpers for accepted V2 isolation evidence."""
import json
import sqlite3
from dataclasses import dataclass

from exchange.isolation_codec import decode_isolation_evidence
from exchange.isolation_envelope import IsolationEvidence
from protocol.quantities import lookup_id

ACCEPTANCE_PREFIX = 'v2'


@dataclass(frozen=True)
class AcceptedEvidence:
    acceptance_id: int
    wire: str
    evidence: IsolationEvidence


def format_acceptance_id(sequence: int) -> str:
    return f'{ACCEPTANCE_PREFIX}:{sequence}'


def _identity_key(evidence: IsolationEvidence):
    # The revision number is only unique inside one site store, so the round
    # and bench identity accompany it to distinguish pieces issued by the
    # independent site databases that converge at the center.
    return (
        evidence.round_id,
        evidence.bench_id,
        evidence.revision_id,
        json.dumps(list(evidence.reference_order), ensure_ascii=False),
        json.dumps(list(evidence.bench_order), ensure_ascii=False),
    )


def parse_acceptance_id(value) -> int:
    """Return the positive sequence of a ``v2:N`` id, else raise ValueError."""
    if not isinstance(value, str):
        raise ValueError('V2 acceptance id must be a v2:N string')
    prefix, separator, sequence = value.partition(':')
    if prefix != ACCEPTANCE_PREFIX or not separator or not sequence:
        raise ValueError('V2 acceptance id must look like v2:1')
    if not sequence.isdigit() or sequence[0] == '0':
        raise ValueError('V2 acceptance id has a leading zero or non-digit sequence')
    number = int(sequence)
    if number < 1:
        raise ValueError('V2 acceptance id sequence must be positive')
    return number


def find_evidence_by_identity(db: sqlite3.Connection, evidence: IsolationEvidence):
    row = db.execute('''
        SELECT acceptance_id, wire FROM accepted_evidence
        WHERE round_id = ? AND bench_id = ? AND revision_id = ?
              AND reference_order = ? AND bench_order = ?
    ''', _identity_key(evidence)).fetchone()
    return None if row is None else _accepted(row)


def insert_evidence(db: sqlite3.Connection, evidence: IsolationEvidence, wire: str) -> int:
    if not db.in_transaction:
        raise RuntimeError('evidence insert requires the caller transaction')
    cursor = db.execute('''
        INSERT INTO accepted_evidence (
            round_id, bench_id, revision_id, reference_order, bench_order, wire
        ) VALUES (?, ?, ?, ?, ?, ?)
    ''', (*_identity_key(evidence), wire))
    return cursor.lastrowid


def _accepted(row) -> AcceptedEvidence:
    acceptance_id, wire = row
    return AcceptedEvidence(acceptance_id, wire, decode_isolation_evidence(wire))


def get_accepted_evidence(db: sqlite3.Connection, acceptance_id) -> AcceptedEvidence:
    """Look up a V2 acceptance id.

    A syntactically valid but unknown id raises :class:`KeyError`; malformed
    ids raise :class:`ValueError`.
    """
    sequence = parse_acceptance_id(acceptance_id)
    lookup_id(sequence)
    row = db.execute('''
        SELECT acceptance_id, wire FROM accepted_evidence WHERE acceptance_id = ?
    ''', (sequence,)).fetchone()
    if row is None:
        raise KeyError(acceptance_id)
    return _accepted(row)
