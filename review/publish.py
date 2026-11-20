import sqlite3

from review.compare import build_comparison_rows
from review.isolation_compare import determine_isolation
from review.isolation_selection import select_evidence
from review.isolation_store import insert_isolation_report, report_to_dict
from review.register import ComparisonReport, insert_comparison
from review.selection import select_summaries


def issue_comparison(db: sqlite3.Connection, first_id: int, second_id: int) -> ComparisonReport:
    db.execute('BEGIN IMMEDIATE')
    with db:
        selection = select_summaries(db, first_id, second_id)
        rows = build_comparison_rows(selection)
        report = insert_comparison(db, selection.round_id, rows)
    return report


def issue_isolation(db: sqlite3.Connection, first_id: str, second_id: str) -> dict:
    """Issue the minimum joint isolation report from two V2 acceptance ids.

    The ids may be passed in either work order slot order.  The report, its
    sources and the receipt are committed together; a SQLite failure rolls the
    whole business write back and the same inputs can be retried afterwards.
    """
    db.execute('BEGIN IMMEDIATE')
    with db:
        selection = select_evidence(db, first_id, second_id)
        outcome = determine_isolation(selection)
        report = insert_isolation_report(db, selection, outcome)
    return report_to_dict(report)
