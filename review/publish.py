import sqlite3

from review.compare import build_comparison_rows
from review.register import ComparisonReport, insert_comparison
from review.selection import select_summaries


def issue_comparison(db: sqlite3.Connection, first_id: int, second_id: int) -> ComparisonReport:
    db.execute('BEGIN IMMEDIATE')
    with db:
        selection = select_summaries(db, first_id, second_id)
        rows = build_comparison_rows(selection)
        report = insert_comparison(db, selection.round_id, rows)
    return report
