import sqlite3
from dataclasses import dataclass
from fractions import Fraction

from intake.freeze import get_frozen_revision
from protocol.rounds import get_round


@dataclass(frozen=True)
class Observation:
    row_name: str
    nominal_residual: Fraction


@dataclass(frozen=True)
class ObservationBatch:
    freeze_id: int
    revision_id: int
    round_id: str
    bench_id: str
    bench_order: tuple[str, str]
    rows: tuple[Observation, ...]


def load_observations(db: sqlite3.Connection, freeze_id: int) -> ObservationBatch:
    frozen = get_frozen_revision(db, freeze_id)
    revision = frozen.revision
    plan = get_round(db, revision.round_id)
    _, nominals = plan.bench(revision.bench_id)
    by_name = {nominal.row_name: nominal.value for nominal in nominals}
    rows = tuple(
        Observation(row.row_name, row.value - by_name[row.row_name])
        for row in revision.rows
    )
    return ObservationBatch(
        frozen.freeze_id, revision.revision_id, plan.round_id, revision.bench_id, plan.bench_order, rows
    )
