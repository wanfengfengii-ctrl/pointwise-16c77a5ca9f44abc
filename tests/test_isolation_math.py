"""Exact rational solver tests: RREF, intersection, minimum supports."""
import unittest
from fractions import Fraction as F

from fit.isolation_relations import (
    AffineRelation,
    intersect_relations,
    minimum_isolation,
    reduced_row_echelon,
    relation_from_equations,
)


def vector(*values):
    return [F(value) for value in values]


class RrefTests(unittest.TestCase):
    def test_rref_uses_exact_fractions(self):
        matrix = [
            [F(1), F(2), F(1), F(3)],
            [F(2), F(-1), F(1), F(1)],
        ]
        reduced = reduced_row_echelon(matrix, 3)
        self.assertEqual(reduced, [
            [F(1), F(0), F(3, 5), F(1)],
            [F(0), F(1), F(1, 5), F(1)],
        ])

    def test_inconsistent_system_becomes_empty(self):
        relation = relation_from_equations([
            (vector(1, 1), F(1)),
            (vector(1, 1), F(2)),
        ], 2)
        self.assertEqual(relation.kind, 'empty')

    def test_zero_equals_nonzero_is_empty(self):
        relation = relation_from_equations([(vector(0, 0), F(3))], 2)
        self.assertEqual(relation.kind, 'empty')

    def test_no_constraints_is_full(self):
        self.assertEqual(relation_from_equations([], 3), AffineRelation('full', 3))
        self.assertEqual(
            relation_from_equations([(vector(0, 0, 0), F(0))], 3),
            AffineRelation('full', 3),
        )


class MinimumIsolationTests(unittest.TestCase):
    def test_zero_feasible(self):
        relation = relation_from_equations([(vector(1, -1), F(0))], 2)
        self.assertEqual(minimum_isolation(relation), (0, frozenset(), True))

    def test_tie_between_two_references(self):
        # X + Y = 1 permits isolating X alone or Y alone: minimum one,
        # but neither reference appears in every minimum explanation.
        relation = relation_from_equations([(vector(1, 1), F(1))], 2)
        count, required, feasible = minimum_isolation(relation)
        self.assertEqual((count, feasible, required), (1, True, frozenset()))

    def test_required_reference_in_all_minima(self):
        # X = 1 with Y free forces X into every feasible explanation.
        relation = relation_from_equations([(vector(1, 0), F(1))], 2)
        count, required, feasible = minimum_isolation(relation)
        self.assertEqual((count, feasible, required), (1, True, frozenset({0})))

    def test_joint_two_required(self):
        first = relation_from_equations([(vector(1, 1), F(1))], 2)
        second = relation_from_equations([(vector(1, -1), F(0))], 2)
        joint = intersect_relations(first, second)
        count, required, feasible = minimum_isolation(joint)
        self.assertEqual((count, feasible, set(required)), (2, True, {0, 1}))

    def test_empty_relation_is_impossible(self):
        empty = AffineRelation('empty', 2)
        self.assertEqual(minimum_isolation(empty), (None, frozenset(), False))
        self.assertEqual(minimum_isolation(intersect_relations(empty, AffineRelation('full', 2)))[2], False)

    def test_three_reference_minimum_and_intersection(self):
        # X + Y + Z = 1 and X + Y - Z = 1 force Z = 0; the minimum support is
        # one (isolate X or Y alone), and Z never appears in a minimum vector.
        first = relation_from_equations([(vector(1, 1, 1), F(1))], 3)
        second = relation_from_equations([(vector(1, 1, -1), F(1))], 3)
        joint = intersect_relations(first, second)
        count, required, feasible = minimum_isolation(joint)
        self.assertEqual((count, feasible, required), (1, True, frozenset()))
        # Adding X = 1 makes X mandatory in every minimum explanation.
        pinned = intersect_relations(joint, relation_from_equations([(vector(1, 0, 0), F(1))], 3))
        count, required, feasible = minimum_isolation(pinned)
        self.assertEqual((count, feasible, required), (1, True, frozenset({0})))

    def test_full_relation_allows_zero(self):
        self.assertEqual(minimum_isolation(AffineRelation('full', 4)), (0, frozenset(), True))

    def test_range_guard(self):
        with self.assertRaises(ValueError):
            relation_from_equations([], 9)


if __name__ == '__main__':
    unittest.main()
