"""Selection of two V2 evidence pieces for a joint isolation review."""
from dataclasses import dataclass

from exchange.isolation_catalog import AcceptedEvidence, get_accepted_evidence


@dataclass(frozen=True)
class IsolationSelection:
    round_id: str
    reference_order: tuple[str, ...]
    evidence: tuple[AcceptedEvidence, AcceptedEvidence]


def select_evidence(db, first_id, second_id) -> IsolationSelection:
    first = get_accepted_evidence(db, first_id)
    second = get_accepted_evidence(db, second_id)
    left, right = first.evidence, second.evidence
    if left.round_id != right.round_id:
        raise ValueError('isolation requires evidence from the same round')
    if left.bench_id == right.bench_id:
        raise ValueError('isolation requires two different benches')
    if left.bench_order != right.bench_order:
        raise ValueError('evidence work order slots disagree')
    if left.reference_order != right.reference_order:
        raise ValueError('evidence reference order disagrees')
    by_bench = {left.bench_id: first, right.bench_id: second}
    return IsolationSelection(
        left.round_id,
        left.reference_order,
        tuple(by_bench[slot_bench] for slot_bench in left.bench_order),
    )
