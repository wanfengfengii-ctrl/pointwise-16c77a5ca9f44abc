import sqlite3
from dataclasses import dataclass

from protocol.quantities import format_rational, lookup_id, parse_rational
from review.compare import BenchStatistics


@dataclass(frozen=True)
class ComparisonReceipt:
    receipt_id: int
    report_id: int
    acceptance_ids: tuple[int, int]


@dataclass(frozen=True)
class ComparisonReport:
    report_id: int
    round_id: str
    rows: tuple[BenchStatistics, BenchStatistics]
    receipt: ComparisonReceipt


def initialize_comparison_store(db: sqlite3.Connection) -> None:
    db.executescript('''
        CREATE TABLE IF NOT EXISTS comparison_reports (
            report_id INTEGER PRIMARY KEY,
            round_id TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS comparison_rows (
            report_id INTEGER NOT NULL REFERENCES comparison_reports(report_id),
            slot INTEGER NOT NULL CHECK (slot IN (0, 1)),
            bench_id TEXT NOT NULL,
            acceptance_id INTEGER NOT NULL REFERENCES accepted_summaries(acceptance_id),
            zero_point TEXT NOT NULL,
            row_count INTEGER NOT NULL CHECK (row_count > 0),
            residual_ss TEXT NOT NULL,
            PRIMARY KEY (report_id, slot),
            UNIQUE (report_id, bench_id),
            UNIQUE (report_id, acceptance_id)
        );
        CREATE TABLE IF NOT EXISTS comparison_receipts (
            receipt_id INTEGER PRIMARY KEY,
            report_id INTEGER NOT NULL UNIQUE REFERENCES comparison_reports(report_id),
            first_acceptance_id INTEGER NOT NULL REFERENCES accepted_summaries(acceptance_id),
            second_acceptance_id INTEGER NOT NULL REFERENCES accepted_summaries(acceptance_id)
        );
    ''')


def initialize_isolation_store(db: sqlite3.Connection) -> None:
    """Create the V2 isolation acceptance, report and receipt tables.

    Re-running the initializer keeps every accepted body, report and receipt
    already stored.
    """
    db.execute('PRAGMA foreign_keys = ON')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS accepted_evidence (
            acceptance_id INTEGER PRIMARY KEY,
            round_id TEXT NOT NULL,
            bench_id TEXT NOT NULL,
            revision_id INTEGER NOT NULL CHECK (revision_id > 0),
            reference_order TEXT NOT NULL,
            bench_order TEXT NOT NULL,
            wire TEXT NOT NULL,
            UNIQUE (round_id, bench_id, revision_id, reference_order, bench_order)
        );
        CREATE TABLE IF NOT EXISTS isolation_reports (
            report_id INTEGER PRIMARY KEY,
            round_id TEXT NOT NULL,
            status TEXT NOT NULL,
            minimum_count INTEGER,
            reference_order TEXT NOT NULL,
            required_references TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS isolation_sources (
            report_id INTEGER NOT NULL REFERENCES isolation_reports(report_id),
            slot INTEGER NOT NULL CHECK (slot IN (0, 1)),
            bench_id TEXT NOT NULL,
            revision_id INTEGER NOT NULL CHECK (revision_id > 0),
            acceptance_id INTEGER NOT NULL REFERENCES accepted_evidence(acceptance_id),
            wire TEXT NOT NULL,
            PRIMARY KEY (report_id, slot),
            UNIQUE (report_id, bench_id),
            UNIQUE (report_id, acceptance_id)
        );
        CREATE TABLE IF NOT EXISTS isolation_receipts (
            receipt_id INTEGER PRIMARY KEY,
            report_id INTEGER NOT NULL UNIQUE REFERENCES isolation_reports(report_id),
            first_acceptance_id INTEGER NOT NULL REFERENCES accepted_evidence(acceptance_id),
            second_acceptance_id INTEGER NOT NULL REFERENCES accepted_evidence(acceptance_id)
        );
    ''')


def insert_comparison(db: sqlite3.Connection, round_id: str,
                      rows: tuple[BenchStatistics, BenchStatistics]) -> ComparisonReport:
    if not db.in_transaction:
        raise RuntimeError('comparison insert requires the caller transaction')
    first, second = rows
    report_id = db.execute('INSERT INTO comparison_reports (round_id) VALUES (?)', (round_id,)).lastrowid
    db.executemany('''
        INSERT INTO comparison_rows (
            report_id, slot, bench_id, acceptance_id, zero_point, row_count, residual_ss
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        (report_id, slot, row.bench_id, row.acceptance_id, format_rational(row.zero_point),
         row.row_count, format_rational(row.residual_ss))
        for slot, row in enumerate(rows)
    ))
    sources = (first.acceptance_id, second.acceptance_id)
    receipt_id = db.execute('''
        INSERT INTO comparison_receipts (report_id, first_acceptance_id, second_acceptance_id)
        VALUES (?, ?, ?)
    ''', (report_id, *sources)).lastrowid
    return ComparisonReport(report_id, round_id, rows, ComparisonReceipt(receipt_id, report_id, sources))


def get_comparison(db: sqlite3.Connection, report_id: int) -> ComparisonReport:
    lookup_id(report_id)
    header = db.execute('''
        SELECT report.round_id, receipt.receipt_id, receipt.first_acceptance_id, receipt.second_acceptance_id
        FROM comparison_reports AS report
        JOIN comparison_receipts AS receipt ON receipt.report_id = report.report_id
        WHERE report.report_id = ?
    ''', (report_id,)).fetchone()
    if header is None:
        raise KeyError(report_id)
    result = db.execute('''
        SELECT bench_id, acceptance_id, zero_point, row_count, residual_ss
        FROM comparison_rows WHERE report_id = ? ORDER BY slot
    ''', (report_id,))
    first, second = (
        BenchStatistics(bench, source, parse_rational(zero), count, parse_rational(squares))
        for bench, source, zero, count, squares in result
    )
    round_id, receipt_id, first_source, second_source = header
    receipt = ComparisonReceipt(receipt_id, report_id, (first_source, second_source))
    return ComparisonReport(report_id, round_id, (first, second), receipt)
