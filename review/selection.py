import sqlite3
from dataclasses import dataclass

from exchange.catalog import AcceptedSummary, get_accepted_summary


@dataclass(frozen=True)
class ComparisonSelection:
    round_id: str
    summaries: tuple[AcceptedSummary, AcceptedSummary]


def select_summaries(db: sqlite3.Connection, first_id: int, second_id: int) -> ComparisonSelection:
    first = get_accepted_summary(db, first_id)
    second = get_accepted_summary(db, second_id)
    left, right = first.summary, second.summary
    if left.round_id != right.round_id:
        raise ValueError('comparison requires summaries from the same round')
    if left.identity.bench_id == right.identity.bench_id:
        raise ValueError('comparison requires two different benches')
    if left.bench_order != right.bench_order:
        raise ValueError('summary work order slots disagree')
    by_bench = {left.identity.bench_id: first, right.identity.bench_id: second}
    first_slot, second_slot = left.bench_order
    return ComparisonSelection(left.round_id, (by_bench[first_slot], by_bench[second_slot]))
