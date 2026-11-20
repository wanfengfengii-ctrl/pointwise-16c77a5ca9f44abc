import sqlite3

from intake.revisions import get_revision


def resolve_correction_parent(db: sqlite3.Connection, round_id: str,
                              bench_id: str, corrects: int | None) -> int | None:
    if corrects is None:
        return None
    parent = get_revision(db, corrects)
    if (parent.round_id, parent.bench_id) != (round_id, bench_id):
        raise ValueError('correction parent belongs to a different round or bench')
    return parent.revision_id
