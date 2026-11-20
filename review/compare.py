from dataclasses import dataclass
from fractions import Fraction

from exchange.catalog import AcceptedSummary
from review.selection import ComparisonSelection


@dataclass(frozen=True)
class BenchStatistics:
    bench_id: str
    acceptance_id: int
    zero_point: Fraction
    row_count: int
    residual_ss: Fraction


def _statistics(accepted: AcceptedSummary) -> BenchStatistics:
    summary = accepted.summary
    return BenchStatistics(
        summary.identity.bench_id, accepted.acceptance_id, summary.zero_point,
        summary.row_count, summary.residual_ss,
    )


def build_comparison_rows(selection: ComparisonSelection) -> tuple[BenchStatistics, BenchStatistics]:
    first, second = selection.summaries
    return _statistics(first), _statistics(second)
