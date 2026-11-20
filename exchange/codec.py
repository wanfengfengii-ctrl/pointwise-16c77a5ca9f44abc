import json

from exchange.envelope import V1_VERSION, IssuerIdentity, V1Summary, validate_summary
from protocol.quantities import format_rational, parse_rational

_FIELDS = {
    'version', 'round_id', 'bench_id', 'local_report_id', 'bench_order',
    'zero_point', 'row_count', 'residual_ss',
}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f'invalid JSON number: {value}')


def encode_summary(summary: V1Summary) -> str:
    validate_summary(summary)
    return json.dumps({
        'version': V1_VERSION,
        'round_id': summary.round_id,
        'bench_id': summary.identity.bench_id,
        'local_report_id': summary.identity.local_report_id,
        'bench_order': summary.bench_order,
        'zero_point': format_rational(summary.zero_point),
        'row_count': summary.row_count,
        'residual_ss': format_rational(summary.residual_ss),
    }, sort_keys=True, separators=(',', ':'))


def decode_summary(wire: str) -> V1Summary:
    if not isinstance(wire, str):
        raise ValueError('V1 body must be JSON text')
    try:
        payload = json.loads(wire, object_pairs_hook=_unique_object, parse_constant=_reject_constant)
    except RecursionError as exc:
        raise ValueError('V1 JSON is too deeply nested') from exc
    if not isinstance(payload, dict) or payload.keys() != _FIELDS:
        raise ValueError('unexpected V1 fields')
    version = payload['version']
    if type(version) is not int or version != V1_VERSION:
        raise ValueError('unsupported summary version')
    order = payload['bench_order']
    if not isinstance(order, list) or len(order) != 2:
        raise ValueError('bench_order must be a two-element array')
    summary = V1Summary(
        IssuerIdentity(payload['bench_id'], payload['local_report_id']),
        payload['round_id'],
        (order[0], order[1]),
        parse_rational(payload['zero_point']),
        payload['row_count'],
        parse_rational(payload['residual_ss']),
    )
    validate_summary(summary)
    return summary
