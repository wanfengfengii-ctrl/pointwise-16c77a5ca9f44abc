"""Persistence and assembly of V2 isolation reports."""
import json
import sqlite3
from dataclasses import dataclass

from exchange.isolation_catalog import format_acceptance_id
from review.isolation_compare import IsolationOutcome


@dataclass(frozen=True)
class IsolationReceipt:
    receipt_id: int
    report_id: int
    acceptance_ids: tuple[str, str]


@dataclass(frozen=True)
class StoredIsolationReport:
    report_id: int
    round_id: str
    reference_order: tuple[str, ...]
    status: str
    minimum_count: int | None
    required_references: tuple[str, ...]
    sources: tuple[dict, dict]
    receipt: IsolationReceipt


def insert_isolation_report(db: sqlite3.Connection, selection,
                            outcome: IsolationOutcome) -> StoredIsolationReport:
    if not db.in_transaction:
        raise RuntimeError('isolation insert requires the caller transaction')
    evidence = selection.evidence
    report_id = db.execute(
        'INSERT INTO isolation_reports (round_id, status, minimum_count, reference_order, required_references) '
        'VALUES (?, ?, ?, ?, ?)',
        (
            selection.round_id,
            outcome.status,
            outcome.minimum_count,
            json.dumps(list(selection.reference_order), ensure_ascii=False),
            json.dumps(list(outcome.required_references), ensure_ascii=False),
        ),
    ).lastrowid
    db.executemany('''
        INSERT INTO isolation_sources (report_id, slot, bench_id, revision_id, acceptance_id, wire)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        (
            report_id,
            slot,
            item.evidence.bench_id,
            item.evidence.revision_id,
            item.acceptance_id,
            item.wire,
        )
        for slot, item in enumerate(evidence)
    ))
    acceptance_ids = tuple(format_acceptance_id(item.acceptance_id) for item in evidence)
    receipt_id = db.execute('''
        INSERT INTO isolation_receipts (report_id, first_acceptance_id, second_acceptance_id)
        VALUES (?, ?, ?)
    ''', (report_id, *(item.acceptance_id for item in evidence))).lastrowid
    return _assemble(
        report_id,
        selection.round_id,
        selection.reference_order,
        outcome,
        evidence,
        IsolationReceipt(receipt_id, report_id, acceptance_ids),
    )


def _assemble(report_id, round_id, reference_order, outcome, evidence, receipt) -> StoredIsolationReport:
    sources = tuple(
        {
            'acceptance_id': format_acceptance_id(item.acceptance_id),
            'bench_id': item.evidence.bench_id,
            'revision_id': item.evidence.revision_id,
            'wire': item.wire,
        }
        for item in evidence
    )
    return StoredIsolationReport(
        report_id,
        round_id,
        tuple(reference_order),
        outcome.status,
        outcome.minimum_count,
        tuple(outcome.required_references),
        sources,
        receipt,
    )


def get_isolation_report(db: sqlite3.Connection, report_id: int) -> StoredIsolationReport:
    from protocol.quantities import lookup_id
    lookup_id(report_id)
    header = db.execute('''
        SELECT round_id, status, minimum_count, reference_order, required_references
        FROM isolation_reports WHERE report_id = ?
    ''', (report_id,)).fetchone()
    if header is None:
        raise KeyError(report_id)
    round_id, status, minimum_count, reference_payload, required_payload = header
    receipt_row = db.execute('''
        SELECT receipt_id, first_acceptance_id, second_acceptance_id
        FROM isolation_receipts WHERE report_id = ?
    ''', (report_id,)).fetchone()
    receipt_id, first_sequence, second_sequence = receipt_row
    source_rows = db.execute('''
        SELECT bench_id, revision_id, acceptance_id, wire
        FROM isolation_sources WHERE report_id = ? ORDER BY slot
    ''', (report_id,)).fetchall()
    sources = tuple(
        {
            'acceptance_id': format_acceptance_id(acceptance_id),
            'bench_id': bench_id,
            'revision_id': revision_id,
            'wire': wire,
        }
        for bench_id, revision_id, acceptance_id, wire in source_rows
    )
    receipt = IsolationReceipt(
        receipt_id,
        report_id,
        (format_acceptance_id(first_sequence), format_acceptance_id(second_sequence)),
    )
    return StoredIsolationReport(
        report_id,
        round_id,
        tuple(json.loads(reference_payload)),
        status,
        minimum_count,
        tuple(json.loads(required_payload)),
        sources,
        receipt,
    )


def report_to_dict(report: StoredIsolationReport) -> dict:
    """The exact dictionary returned by issue and readback entry points."""
    return {
        'report_id': report.report_id,
        'round_id': report.round_id,
        'reference_order': list(report.reference_order),
        'status': report.status,
        'minimum_count': report.minimum_count,
        'required_references': list(report.required_references),
        'sources': [dict(source) for source in report.sources],
        'receipt': {
            'receipt_id': report.receipt.receipt_id,
            'report_id': report.receipt.report_id,
            'acceptance_ids': list(report.receipt.acceptance_ids),
        },
    }
