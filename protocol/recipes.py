from dataclasses import dataclass
from fractions import Fraction

from protocol.quantities import parse_rational
from protocol.references import ReferenceSet, named_pairs, require_name


@dataclass(frozen=True)
class RecipeTerm:
    reference: str
    sensitivity: Fraction


@dataclass(frozen=True)
class RecipeLine:
    name: str
    terms: tuple[RecipeTerm, ...]


@dataclass(frozen=True)
class BenchRecipe:
    bench_id: str
    lines: tuple[RecipeLine, ...]


def build_bench_recipe(bench_id: str, rows, references: ReferenceSet) -> BenchRecipe:
    require_name(bench_id, 'bench')
    known = references.nominal_by_name()
    lines = []
    for row_name, coefficients in named_pairs(rows, 'recipe line'):
        terms = []
        for reference, coefficient in named_pairs(coefficients, 'recipe reference'):
            if reference not in known:
                raise ValueError(f'unknown recipe reference: {reference}')
            terms.append(RecipeTerm(reference, parse_rational(coefficient)))
        if not terms:
            raise ValueError(f'recipe line has no terms: {row_name}')
        lines.append(RecipeLine(row_name, tuple(terms)))
    if not lines:
        raise ValueError(f'bench has no recipe lines: {bench_id}')
    return BenchRecipe(bench_id, tuple(lines))
