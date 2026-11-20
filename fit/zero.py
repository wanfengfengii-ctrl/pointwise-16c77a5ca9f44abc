from fractions import Fraction

from fit.observations import ObservationBatch


def estimate_zero(observations: ObservationBatch) -> Fraction:
    if not observations.rows:
        raise ValueError('a local estimate requires at least one reading')
    total = sum((row.nominal_residual for row in observations.rows), Fraction(0))
    return total / len(observations.rows)
