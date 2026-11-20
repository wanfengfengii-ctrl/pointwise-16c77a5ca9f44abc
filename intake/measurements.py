import sqlite3

from intake.corrections import resolve_correction_parent
from intake.revisions import save_revision
from intake.row_binding import bind_reading_rows
from protocol.rounds import get_round


def record_readings(db: sqlite3.Connection, round_id: str, bench_id: str,
                    readings, *, corrects: int | None = None) -> int:
    plan = get_round(db, round_id)
    recipe, _ = plan.bench(bench_id)
    parent_id = resolve_correction_parent(db, round_id, bench_id, corrects)
    rows = bind_reading_rows(recipe, readings)
    return save_revision(db, round_id, bench_id, parent_id, rows)
