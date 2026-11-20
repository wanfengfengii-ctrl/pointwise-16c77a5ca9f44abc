from fractions import Fraction as F

from protocol.quantities import READING_UNIT, format_rational, parse_rational
from protocol.rounds import get_round, register_round
from tests.support import CalibrationCase, LEFT, RIGHT, ROUND, counts, example_benches, register_example


class ProtocolTests(CalibrationCase):
    def setUp(self):
        super().setUp()
        self.site = self.open_site(LEFT)

    def test_fixed_nominal(self):
        written = register_example(self.site)
        plan = get_round(self.site, ROUND)
        self.assertEqual(plan, written)
        self.assertEqual(plan.bench_order, (LEFT, RIGHT))
        self.assertEqual([(ref.name, ref.nominal) for ref in plan.references.entries], [('X', F(2)), ('Y', F(3))])
        recipe, nominals = plan.bench(LEFT)
        self.assertEqual([line.name for line in recipe.lines], ['a', 'b', 'half'])
        self.assertEqual([(row.row_name, row.value) for row in nominals[:2]], [('a', F(-1)), ('b', F(2))])
        self.assertEqual(READING_UNIT, 'µm')

    def test_signed_fraction(self):
        register_example(self.site)
        recipe, nominals = get_round(self.site, ROUND).bench(LEFT)
        self.assertEqual([(term.reference, term.sensitivity) for term in recipe.lines[2].terms], [
            ('X', F(1, 2)), ('Y', F(-1, 2))
        ])
        self.assertEqual((nominals[2].row_name, nominals[2].value), ('half', F(-1, 2)))
        self.assertEqual(format_rational(parse_rational(' -0.50 ')), '-1/2')
        self.assertEqual(parse_rational('2/-4'), F(-1, 2))
        self.assertEqual(parse_rational(F(2, 3)), F(2, 3))
        self.assertEqual(parse_rational(0), F(0))

    def test_round_history(self):
        older = register_example(self.site)
        register_example(self.site, 'shift-2', x=7)
        self.assertEqual(get_round(self.site, ROUND), older)
        self.assertEqual(get_round(self.site, ROUND).bench(LEFT)[1][0].value, F(-1))
        self.assertEqual(get_round(self.site, 'shift-2').bench(LEFT)[1][0].value, F(4))

    def test_bad_reference(self):
        benches = (example_benches()[0], (RIGHT, (('a', (('unlisted', 1),)),)))
        with self.assertRaises(ValueError):
            register_round(self.site, ROUND, (('X', 2), ('Y', 3)), benches)
        with self.assertRaises(KeyError):
            get_round(self.site, ROUND)
        self.assertEqual(counts(self.site, 'rounds'), (0,))

    def test_invalid_round(self):
        original = register_example(self.site)
        benches = example_benches()
        for value in (None, True, 0.5, '', '1/0', 'bad'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                register_round(self.site, 'bad', (('X', value), ('Y', 3)), benches)
        refs = (('X', 2), ('Y', 3))
        invalid_benches = (
            (benches[0], benches[0]),
            (benches[0],),
            ((LEFT, (('a', (('X', 1),)), ('a', (('Y', 1),)))), benches[1]),
            ((LEFT, (('a', (('X', 1), ('X', -1))),)), benches[1]),
            ((LEFT, (('a', (('X', '1/0'),)),)), benches[1]),
        )
        for invalid in invalid_benches:
            with self.subTest(benches=invalid), self.assertRaises(ValueError):
                register_round(self.site, 'bad', refs, invalid)
        with self.assertRaises(ValueError):
            register_round(self.site, 'bad', (('X', 2), ('X', 7)), benches)
        with self.assertRaises(ValueError):
            register_example(self.site, x=7)
        with self.assertRaises(KeyError):
            get_round(self.site, 'bad')
        self.assertEqual(get_round(self.site, ROUND), original)
        self.assertEqual(counts(self.site, 'rounds'), (1,))
