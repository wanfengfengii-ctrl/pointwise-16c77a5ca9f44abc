from dataclasses import dataclass
from fractions import Fraction

from fit.observations import ObservationBatch


@dataclass(frozen=True)
class RowDeviation:
    row_name: str
    deviation: Fraction


@dataclass(frozen=True)
class ResidualStatistics:
    row_count: int
    residual_ss: Fraction
    deviations: tuple[RowDeviation, ...]


def summarize_residuals(observations: ObservationBatch, zero_point: Fraction) -> ResidualStatistics:
    deviations = tuple(
        RowDeviation(row.row_name, row.nominal_residual - zero_point)
        for row in observations.rows
    )
    squares = sum((row.deviation ** 2 for row in deviations), Fraction(0))
    return ResidualStatistics(len(deviations), squares, deviations)
