import sqlite3

from exchange.codec import encode_summary
from exchange.envelope import IssuerIdentity, V1Summary
from fit.local_reports import get_local_report


def issue_summary(db: sqlite3.Connection, local_report_id: int) -> str:
    report = get_local_report(db, local_report_id)
    return encode_summary(V1Summary(
        IssuerIdentity(report.bench_id, report.report_id), report.round_id,
        report.bench_order, report.zero_point, report.statistics.row_count,
        report.statistics.residual_ss,
    ))
