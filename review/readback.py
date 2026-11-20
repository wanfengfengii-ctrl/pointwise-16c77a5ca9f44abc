import sqlite3
from dataclasses import dataclass

from exchange.catalog import AcceptedSummary, get_accepted_summary
from review.register import ComparisonReport, get_comparison


@dataclass(frozen=True)
class ComparisonReadback:
    report: ComparisonReport
    summaries: tuple[AcceptedSummary, AcceptedSummary]


def read_comparison(db: sqlite3.Connection, report_id: int) -> ComparisonReadback:
    report = get_comparison(db, report_id)
    first, second = report.rows
    return ComparisonReadback(report, (
        get_accepted_summary(db, first.acceptance_id),
        get_accepted_summary(db, second.acceptance_id),
    ))
