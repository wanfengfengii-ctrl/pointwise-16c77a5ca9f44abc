from dataclasses import dataclass
from fractions import Fraction

from protocol.quantities import parse_rational
from protocol.recipes import BenchRecipe
from protocol.references import named_pairs


@dataclass(frozen=True)
class BoundReading:
    row_name: str
    position: int
    value: Fraction


def bind_reading_rows(recipe: BenchRecipe, readings) -> tuple[BoundReading, ...]:
    submitted = dict(named_pairs(readings, 'reading row'))
    unknown = submitted.keys() - {line.name for line in recipe.lines}
    if unknown:
        raise ValueError(f'rows outside bench recipe: {sorted(unknown)!r}')
    return tuple(
        BoundReading(line.name, position, parse_rational(submitted[line.name]))
        for position, line in enumerate(recipe.lines)
        if line.name in submitted
    )
