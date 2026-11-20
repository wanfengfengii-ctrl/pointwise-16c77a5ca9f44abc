"""Exact JSON codec for V2 isolation evidence."""
import json

from exchange.isolation_envelope import (
    V2_VERSION,
    IsolationEvidence,
    validate_evidence,
)
from fit.isolation_relations import (
    EMPTY_RELATION,
    FULL_RELATION,
    RELATION_KINDS,
    SYSTEM_RELATION,
    V2_MAX_REFERENCES,
    V2_MIN_REFERENCES,
    AffineRelation,
    relation_from_equations,
)
from protocol.quantities import format_rational, parse_rational

_FIELDS = {
    'version', 'round_id', 'bench_id', 'revision_id', 'bench_order',
    'reference_order', 'relation',
}
_RELATION_FIELDS = {'kind', 'equations'}
_EQUATION_FIELDS = {'coefficients', 'rhs'}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f'invalid JSON number: {value}')


def _encode_relation(relation: AffineRelation):
    if relation.kind in (FULL_RELATION, EMPTY_RELATION):
        return {'kind': relation.kind}
    return {
        'kind': SYSTEM_RELATION,
        'equations': [
            {
                'coefficients': [format_rational(value) for value in coefficients],
                'rhs': format_rational(rhs),
            }
            for coefficients, rhs in relation.equations
        ],
    }


def encode_isolation_evidence(evidence: IsolationEvidence) -> str:
    validate_evidence(evidence)
    payload = {
        'version': V2_VERSION,
        'round_id': evidence.round_id,
        'bench_id': evidence.bench_id,
        'revision_id': evidence.revision_id,
        'bench_order': list(evidence.bench_order),
        'reference_order': list(evidence.reference_order),
        'relation': _encode_relation(evidence.relation),
    }
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def _decode_relation(payload, dimension: int) -> AffineRelation:
    if not isinstance(payload, dict):
        raise ValueError('relation must be an object')
    kind = payload.get('kind')
    if kind not in RELATION_KINDS or set(payload) - _RELATION_FIELDS:
        raise ValueError('unsupported relation representation')
    if kind in (FULL_RELATION, EMPTY_RELATION):
        if set(payload) != {'kind'}:
            raise ValueError(f'{kind} relation carries no equations')
        return AffineRelation(kind, dimension)
    equations_payload = payload.get('equations')
    if set(payload) != _RELATION_FIELDS or not isinstance(equations_payload, list) or not equations_payload:
        raise ValueError('system relation requires a non-empty equations array')
    equations = []
    for equation in equations_payload:
        if not isinstance(equation, dict) or set(equation) != _EQUATION_FIELDS:
            raise ValueError('relation equation requires coefficients and rhs')
        coefficients_payload = equation['coefficients']
        if not isinstance(coefficients_payload, list) or len(coefficients_payload) != dimension:
            raise ValueError('relation equation coordinates do not match the reference order')
        coefficients = tuple(parse_rational(value) for value in coefficients_payload)
        rhs = parse_rational(equation['rhs'])
        # Canonical RREF never carries an all-zero coefficient row; an
        # inconsistent relation is expressed via the explicit empty kind.
        if not any(value != 0 for value in coefficients):
            raise ValueError('relation equations require at least one nonzero coefficient')
        equations.append((coefficients, rhs))
    # Re-canonicalize so the representation stays exact and internally coherent;
    # an inconsistent system normalizes to the explicit empty relation.
    return relation_from_equations(equations, dimension)


def decode_isolation_evidence(wire: str) -> IsolationEvidence:
    if not isinstance(wire, str):
        raise ValueError('V2 body must be JSON text')
    try:
        payload = json.loads(wire, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except RecursionError as exc:
        raise ValueError('V2 JSON is too deeply nested') from exc
    except json.JSONDecodeError as exc:
        raise ValueError('malformed V2 JSON body') from exc
    if not isinstance(payload, dict) or payload.keys() != _FIELDS:
        raise ValueError('unexpected V2 fields')
    version = payload['version']
    if type(version) is not int or version != V2_VERSION:
        raise ValueError('unsupported isolation evidence version')
    bench_order = payload['bench_order']
    if not isinstance(bench_order, list) or len(bench_order) != 2:
        raise ValueError('bench_order must be a two-element array')
    reference_order = payload['reference_order']
    if not isinstance(reference_order, list) or not V2_MIN_REFERENCES <= len(reference_order) <= V2_MAX_REFERENCES:
        raise ValueError('V2 reference order must contain 1 to 8 names')
    if len(set(reference_order)) != len(reference_order):
        raise ValueError('reference order contains duplicate names')
    evidence = IsolationEvidence(
        payload['round_id'],
        payload['bench_id'],
        payload['revision_id'],
        (bench_order[0], bench_order[1]),
        tuple(reference_order),
        _decode_relation(payload['relation'], len(reference_order)),
    )
    validate_evidence(evidence)
    return evidence
