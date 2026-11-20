import sqlite3
from dataclasses import dataclass

from exchange.catalog import AcceptedSummary, get_accepted_summary
from review.isolation_store import get_isolation_report, report_to_dict
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


def read_isolation(db: sqlite3.Connection, report_id: int) -> dict:
    """Return the stored isolation report dictionary by its positive number.

    The report is rebuilt from stored values, so it remains available after
    the site stores close and the center store is reopened.
    """
    return report_to_dict(get_isolation_report(db, report_id))
