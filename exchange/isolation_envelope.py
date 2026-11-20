"""V2 isolation evidence envelope and exact relation representation.

The wire format is a JSON object with exactly the fields

    version, round_id, bench_id, revision_id, bench_order,
    reference_order, relation

and ``relation`` is one of

    {"kind": "full"}
    {"kind": "empty"}
    {"kind": "system",
     "equations": [{"coefficients": [...rationals...], "rhs": "...rational..."}]}

The full space and the empty relation are therefore distinguishable from any
non-trivial equation system.  Rationals follow the V1 input rules (integers,
:class:`fractions.Fraction` or exact rational text) and are emitted as
reduced fraction text.
"""
from dataclasses import dataclass
from fractions import Fraction

from fit.isolation_relations import (
    RELATION_KINDS,
    SYSTEM_RELATION,
    V2_MAX_REFERENCES,
    AffineRelation,
)

V2_VERSION = 2


@dataclass(frozen=True)
class IsolationEvidence:
    round_id: str
    bench_id: str
    revision_id: int
    bench_order: tuple[str, str]
    reference_order: tuple[str, ...]
    relation: AffineRelation


def _check_name(value, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'invalid {label}')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise ValueError(f'invalid {label}') from exc


def validate_evidence(evidence: IsolationEvidence) -> None:
    if not isinstance(evidence, IsolationEvidence):
        raise ValueError('expected a V2 isolation evidence envelope')
    _check_name(evidence.round_id, 'round')
    _check_name(evidence.bench_id, 'issuing bench')
    if type(evidence.revision_id) is not int or not 1 <= evidence.revision_id <= 2**63 - 1:
        raise ValueError('invalid revision number')
    if not isinstance(evidence.bench_order, tuple) or len(evidence.bench_order) != 2:
        raise ValueError('evidence requires two ordered work order benches')
    first_bench, second_bench = evidence.bench_order
    _check_name(first_bench, 'first bench')
    _check_name(second_bench, 'second bench')
    if first_bench == second_bench or evidence.bench_id not in evidence.bench_order:
        raise ValueError('issuer does not match two distinct work order slots')
    if not isinstance(evidence.reference_order, tuple) or not evidence.reference_order:
        raise ValueError('evidence requires an ordered reference list')
    if len(evidence.reference_order) > V2_MAX_REFERENCES:
        raise ValueError('V2 rounds support 1 to 8 ordered references')
    if len(set(evidence.reference_order)) != len(evidence.reference_order):
        raise ValueError('reference order contains duplicate names')
    for name in evidence.reference_order:
        _check_name(name, 'reference')
    relation = evidence.relation
    if not isinstance(relation, AffineRelation) or relation.kind not in RELATION_KINDS:
        raise ValueError('invalid isolation relation')
    if relation.dimension != len(evidence.reference_order):
        raise ValueError('relation dimension does not match the reference order')
    if relation.kind == SYSTEM_RELATION:
        if not relation.equations:
            raise ValueError('system relation requires equations')
        for coefficients, rhs in relation.equations:
            if len(coefficients) != relation.dimension or not any(value != 0 for value in coefficients):
                raise ValueError('invalid relation equation coordinates')
            if not isinstance(rhs, Fraction):
                raise ValueError('invalid relation rhs')
            if any(not isinstance(value, Fraction) for value in coefficients):
                raise ValueError('invalid relation coefficients')
