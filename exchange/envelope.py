from dataclasses import dataclass
from fractions import Fraction

V1_VERSION = 1


@dataclass(frozen=True)
class IssuerIdentity:
    bench_id: str
    local_report_id: int


@dataclass(frozen=True)
class V1Summary:
    identity: IssuerIdentity
    round_id: str
    bench_order: tuple[str, str]
    zero_point: Fraction
    row_count: int
    residual_ss: Fraction


def _check_name(value, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'invalid {label}')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise ValueError(f'invalid {label}') from exc


def validate_summary(summary: V1Summary) -> None:
    if not isinstance(summary, V1Summary) or not isinstance(summary.identity, IssuerIdentity):
        raise ValueError('expected a V1 summary with an issuer')
    identity = summary.identity
    _check_name(identity.bench_id, 'issuing bench')
    _check_name(summary.round_id, 'round')
    if type(identity.local_report_id) is not int or not 1 <= identity.local_report_id <= 2**63 - 1:
        raise ValueError('invalid local report number')
    if not isinstance(summary.bench_order, tuple) or len(summary.bench_order) != 2:
        raise ValueError('summary requires two ordered benches')
    first, second = summary.bench_order
    _check_name(first, 'first bench')
    _check_name(second, 'second bench')
    if first == second or identity.bench_id not in summary.bench_order:
        raise ValueError('issuer does not match two distinct work order slots')
    if type(summary.row_count) is not int or summary.row_count < 1:
        raise ValueError('summary requires a positive row count')
    if not isinstance(summary.zero_point, Fraction):
        raise ValueError('invalid zero point')
    if not isinstance(summary.residual_ss, Fraction) or summary.residual_ss < 0:
        raise ValueError('invalid residual sum of squares')
