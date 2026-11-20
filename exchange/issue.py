import sqlite3

from exchange.codec import encode_summary
from exchange.envelope import IssuerIdentity, V1Summary
from exchange.isolation_codec import encode_isolation_evidence
from exchange.isolation_envelope import IsolationEvidence
from fit.isolation_relations import build_station_relation
from fit.local_reports import get_local_report
from intake.freeze import get_frozen_revision
from protocol.rounds import get_round


def issue_summary(db: sqlite3.Connection, local_report_id: int) -> str:
    report = get_local_report(db, local_report_id)
    return encode_summary(V1Summary(
        IssuerIdentity(report.bench_id, report.report_id), report.round_id,
        report.bench_order, report.zero_point, report.statistics.row_count,
        report.statistics.residual_ss,
    ))


def issue_isolation_evidence(db: sqlite3.Connection, freeze_id: int) -> str:
    """Issue the V2 evidence body for an existing frozen revision.

    The frozen revision must belong to a V2 round with 1..8 ordered
    references.  The body carries only the exact feasible deviation
    relation; readings, residuals, row names and recipes stay on the site.
    """
    frozen = get_frozen_revision(db, freeze_id)
    revision = frozen.revision
    plan = get_round(db, revision.round_id)
    relation = build_station_relation(db, freeze_id)
    evidence = IsolationEvidence(
        plan.round_id,
        revision.bench_id,
        revision.revision_id,
        plan.bench_order,
        tuple(entry.name for entry in plan.references.entries),
        relation,
    )
    return encode_isolation_evidence(evidence)
