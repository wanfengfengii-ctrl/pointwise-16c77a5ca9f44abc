from dataclasses import dataclass
from fractions import Fraction

from protocol.recipes import BenchRecipe
from protocol.references import ReferenceSet


@dataclass(frozen=True)
class LineNominal:
    row_name: str
    value: Fraction


def calculate_nominals(references: ReferenceSet, recipe: BenchRecipe) -> tuple[LineNominal, ...]:
    by_name = references.nominal_by_name()
    return tuple(
        LineNominal(
            line.name,
            sum((by_name[term.reference] * term.sensitivity for term in line.terms), Fraction(0)),
        )
        for line in recipe.lines
    )
