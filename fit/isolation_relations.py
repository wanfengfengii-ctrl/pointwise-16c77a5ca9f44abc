"""Exact rational affine relations for V2 isolation evidence.

A station relation describes every common deviation vector
``delta = (delta_1, ..., delta_n)`` for which the station has a single
independent zero point satisfying all measured rows.  Row residuals satisfy

    residual_i = zero + sensitivities_i . delta.

Subtracting the first row removes the station's zero point, so the feasible
deviation vectors form an affine subspace over the rationals, represented by
reduced row echelon linear equations

    coefficients . delta = rhs.

Three relation kinds are distinguished explicitly:

* ``full``   : every deviation vector is feasible (no constraint);
* ``empty``  : no deviation vector is feasible (contradictory readings);
* ``system`` : a non-empty RREF equation system over Q^n.

All arithmetic uses :class:`fractions.Fraction`; n is limited to the V2 range
of 1..8 ordered references.
"""
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

from fit.observations import load_observations
from protocol.rounds import get_round

V2_MIN_REFERENCES = 1
V2_MAX_REFERENCES = 8

FULL_RELATION = 'full'
EMPTY_RELATION = 'empty'
SYSTEM_RELATION = 'system'
RELATION_KINDS = (FULL_RELATION, EMPTY_RELATION, SYSTEM_RELATION)


@dataclass(frozen=True)
class AffineRelation:
    """Canonical affine relation in the V2 reference coordinate order."""

    kind: str
    dimension: int
    # RREF rows as ``(coefficients, rhs)``; empty unless kind == SYSTEM_RELATION.
    equations: tuple[tuple[tuple[Fraction, ...], Fraction], ...] = ()

    def is_consistent(self) -> bool:
        return self.kind != EMPTY_RELATION


def _zero_row(width: int) -> list[Fraction]:
    return [Fraction(0) for _ in range(width)]


def reduced_row_echelon(matrix, width: int) -> list[list[Fraction]]:
    """Return the reduced row echelon form of an augmented rational matrix.

    Each row holds ``width`` coefficient columns followed by one rhs column.
    """
    rows = [list(row) for row in matrix]
    if rows and any(len(row) != width + 1 for row in rows):
        raise ValueError('each equation requires one coefficient per reference plus an rhs')
    pivot_row = 0
    for column in range(width):
        candidate = next(
            (index for index in range(pivot_row, len(rows)) if rows[index][column] != 0),
            None,
        )
        if candidate is None:
            continue
        rows[pivot_row], rows[candidate] = rows[candidate], rows[pivot_row]
        pivot = rows[pivot_row][column]
        rows[pivot_row] = [entry / pivot for entry in rows[pivot_row]]
        for index, row in enumerate(rows):
            if index != pivot_row and row[column] != 0:
                factor = row[column]
                rows[index] = [
                    entry - factor * pivot_entry
                    for entry, pivot_entry in zip(row, rows[pivot_row], strict=True)
                ]
        pivot_row += 1
    return rows


def relation_from_equations(equations, dimension: int) -> AffineRelation:
    """Canonicalize raw affine equations into an :class:`AffineRelation`."""
    if not V2_MIN_REFERENCES <= dimension <= V2_MAX_REFERENCES:
        raise ValueError('V2 rounds support 1 to 8 ordered references')
    # Keep every equation: an all-zero coefficient row with a nonzero rhs is
    # the witness of an inconsistent (empty) relation and must survive.
    augmented = [[*coefficients, rhs] for coefficients, rhs in equations]
    if not augmented:
        return AffineRelation(FULL_RELATION, dimension)
    reduced = reduced_row_echelon(augmented, dimension)
    for row in reduced:
        if all(entry == 0 for entry in row[:dimension]) and row[dimension] != 0:
            return AffineRelation(EMPTY_RELATION, dimension)
    canonical = tuple(
        (tuple(row[:dimension]), row[dimension])
        for row in reduced
        if any(entry != 0 for entry in row[:dimension])
    )
    if not canonical:
        return AffineRelation(FULL_RELATION, dimension)
    return AffineRelation(SYSTEM_RELATION, dimension, canonical)


def build_station_relation(db, freeze_id: int) -> AffineRelation:
    """Derive the exact feasible deviation relation for a frozen revision."""
    observations = load_observations(db, freeze_id)
    plan = get_round(db, observations.round_id)
    recipe, _ = plan.bench(observations.bench_id)
    dimension = len(plan.references.entries)
    if not V2_MIN_REFERENCES <= dimension <= V2_MAX_REFERENCES:
        raise ValueError('V2 rounds support 1 to 8 ordered references')
    if len(observations.rows) <= 1:
        # A single row (or an empty revision, which cannot be frozen) imposes
        # no condition because the station zero is free to absorb the residual.
        return AffineRelation(FULL_RELATION, dimension)
    index_by_name = {entry.name: position for position, entry in enumerate(plan.references.entries)}
    sensitivity_by_row = {}
    for line in recipe.lines:
        vector = _zero_row(dimension)
        for term in line.terms:
            vector[index_by_name[term.reference]] = term.sensitivity
        sensitivity_by_row[line.name] = vector
    base = observations.rows[0]
    base_vector = sensitivity_by_row[base.row_name]
    equations = []
    for observation in observations.rows[1:]:
        vector = sensitivity_by_row[observation.row_name]
        coefficients = [
            vector[position] - base_vector[position] for position in range(dimension)
        ]
        rhs = observation.nominal_residual - base.nominal_residual
        equations.append((coefficients, rhs))
    return relation_from_equations(equations, dimension)


def intersect_relations(first: AffineRelation, second: AffineRelation) -> AffineRelation:
    """Intersect two relations expressed in the same reference coordinates."""
    if first.dimension != second.dimension:
        raise ValueError('relations require matching reference coordinates')
    if first.kind == EMPTY_RELATION or second.kind == EMPTY_RELATION:
        return AffineRelation(EMPTY_RELATION, first.dimension)
    equations = first.equations + second.equations
    return relation_from_equations(equations, first.dimension)


def _all_zero(relation: AffineRelation) -> bool:
    if relation.kind == EMPTY_RELATION:
        return False
    if relation.kind == FULL_RELATION:
        return True
    return all(rhs == 0 for _, rhs in relation.equations)


def minimum_isolation(relation: AffineRelation):
    """Return ``(minimum_count, required_names_positions, feasible)``.

    Enumerates deviation supports from smallest to largest.  A subset is
    feasible when the relation restricted to those coordinates (all other
    deviations fixed at zero) is consistent.  With at most eight references
    the exhaustive enumeration stays small (at most 256 subsets).
    """
    dimension = relation.dimension
    if relation.kind == EMPTY_RELATION:
        return None, frozenset(), False
    if _all_zero(relation):
        return 0, frozenset(), True
    for size in range(1, dimension + 1):
        feasible_sets = []
        for support in combinations(range(dimension), size):
            chosen = frozenset(support)
            restricted = _restrict(relation, chosen)
            if restricted.kind != EMPTY_RELATION:
                feasible_sets.append(chosen)
        if feasible_sets:
            required = frozenset.intersection(*feasible_sets)
            return size, required, True
    # Every non-empty support failed while zero was infeasible: no solution.
    return None, frozenset(), False


def _restrict(relation: AffineRelation, support: frozenset) -> AffineRelation:
    """Fix coordinates outside ``support`` to zero and re-check feasibility."""
    if relation.kind == FULL_RELATION:
        return relation
    if relation.kind == EMPTY_RELATION:
        return relation
    equations = []
    for coefficients, rhs in relation.equations:
        kept = [
            coefficients[position] if position in support else Fraction(0)
            for position in range(relation.dimension)
        ]
        equations.append((kept, rhs))
    return relation_from_equations(equations, relation.dimension)
