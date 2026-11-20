import sqlite3
from dataclasses import dataclass
from fractions import Fraction

from fit.observations import load_observations
from fit.residuals import ResidualStatistics, RowDeviation, summarize_residuals
from fit.zero import estimate_zero
from protocol.quantities import format_rational, lookup_id, parse_rational


@dataclass(frozen=True)
class LocalReport:
    report_id: int
    freeze_id: int
    revision_id: int
    round_id: str
    bench_id: str
    bench_order: tuple[str, str]
    zero_point: Fraction
    statistics: ResidualStatistics


def initialize_local_report_store(db: sqlite3.Connection) -> None:
    db.executescript('''
        CREATE TABLE IF NOT EXISTS local_reports (
            report_id INTEGER PRIMARY KEY,
            freeze_id INTEGER NOT NULL REFERENCES frozen_revisions(freeze_id),
            revision_id INTEGER NOT NULL REFERENCES reading_revisions(revision_id),
            round_id TEXT NOT NULL REFERENCES rounds(round_id),
            bench_id TEXT NOT NULL,
            first_bench TEXT NOT NULL,
            second_bench TEXT NOT NULL,
            zero_point TEXT NOT NULL,
            row_count INTEGER NOT NULL CHECK (row_count > 0),
            residual_ss TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS local_deviations (
            report_id INTEGER NOT NULL REFERENCES local_reports(report_id),
            position INTEGER NOT NULL CHECK (position >= 0),
            row_name TEXT NOT NULL,
            deviation TEXT NOT NULL,
            PRIMARY KEY (report_id, position),
            UNIQUE (report_id, row_name)
        );
    ''')


def issue_local(db: sqlite3.Connection, freeze_id: int) -> LocalReport:
    observations = load_observations(db, freeze_id)
    zero_point = estimate_zero(observations)
    statistics = summarize_residuals(observations, zero_point)
    db.execute('BEGIN IMMEDIATE')
    with db:
        cursor = db.execute('''
            INSERT INTO local_reports (
                freeze_id, revision_id, round_id, bench_id, first_bench, second_bench,
                zero_point, row_count, residual_ss
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            observations.freeze_id, observations.revision_id, observations.round_id,
            observations.bench_id, *observations.bench_order, format_rational(zero_point),
            statistics.row_count, format_rational(statistics.residual_ss),
        ))
        report_id = cursor.lastrowid
        db.executemany('''
            INSERT INTO local_deviations (report_id, position, row_name, deviation) VALUES (?, ?, ?, ?)
        ''', (
            (report_id, position, row.row_name, format_rational(row.deviation))
            for position, row in enumerate(statistics.deviations)
        ))
    return LocalReport(
        report_id, observations.freeze_id, observations.revision_id, observations.round_id,
        observations.bench_id, observations.bench_order, zero_point, statistics,
    )


def get_local_report(db: sqlite3.Connection, report_id: int) -> LocalReport:
    lookup_id(report_id)
    row = db.execute('''
        SELECT freeze_id, revision_id, round_id, bench_id, first_bench, second_bench,
               zero_point, row_count, residual_ss
        FROM local_reports WHERE report_id = ?
    ''', (report_id,)).fetchone()
    if row is None:
        raise KeyError(report_id)
    freeze_id, revision_id, round_id, bench_id, first, second, zero, count, squares = row
    result = db.execute('''
        SELECT row_name, deviation FROM local_deviations WHERE report_id = ? ORDER BY position
    ''', (report_id,))
    deviations = tuple(RowDeviation(name, parse_rational(value)) for name, value in result)
    return LocalReport(
        report_id, freeze_id, revision_id, round_id, bench_id, (first, second),
        parse_rational(zero), ResidualStatistics(count, parse_rational(squares), deviations),
    )
