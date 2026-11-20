import json
from fractions import Fraction as F

from exchange.accept import accept_summary
from exchange.catalog import get_accepted_summary
from exchange.issue import issue_summary
from review.publish import issue_comparison
from review.readback import read_comparison
from tests.support import CalibrationCase, LEFT, LEFT_READINGS, RIGHT, RIGHT_READINGS, counts, make_summary


class ExchangeTests(CalibrationCase):
    def setUp(self):
        super().setUp()
        self.left, self.right = self.two_sites()
        self.center = self.open_center()
        _, self.wire = make_summary(self.left, LEFT, LEFT_READINGS)

    def test_conflict(self):
        accepted = accept_summary(self.center, self.wire)
        self.assertEqual(accept_summary(self.center, self.wire), accepted)
        conflict = json.loads(self.wire)
        conflict['zero_point'] = '7/2'
        with self.assertRaises(ValueError):
            accept_summary(self.center, json.dumps(conflict))
        first = get_accepted_summary(self.center, accepted)
        self.assertEqual(first.wire, self.wire)
        self.assertEqual(first.summary.zero_point, F(1, 2))
        self.assertEqual(counts(self.center, 'accepted_summaries'), (1,))

    def test_equivalent_wire(self):
        original_id = accept_summary(self.center, self.wire)
        payload = dict(reversed(list(json.loads(self.wire).items())))
        payload['zero_point'] = '2/4'
        payload['residual_ss'] = '0.50'
        equivalent = json.dumps(payload, indent=2)
        self.assertNotEqual(equivalent, self.wire)
        self.assertEqual(accept_summary(self.center, equivalent), original_id)
        self.assertEqual(get_accepted_summary(self.center, original_id).wire, self.wire)
        self.assertEqual(counts(self.center, 'accepted_summaries'), (1,))

    def test_first_body(self):
        payload = json.loads(self.wire)
        payload['zero_point'] = '2/4'
        first_body = '  ' + json.dumps(payload, indent=2) + '\n'
        first_id = accept_summary(self.center, first_body)
        self.assertEqual(accept_summary(self.center, self.wire), first_id)
        payload['zero_point'] = '7/2'
        with self.assertRaises(ValueError):
            accept_summary(self.center, json.dumps(payload))
        _, right_wire = make_summary(self.right, RIGHT, RIGHT_READINGS)
        second_id = accept_summary(self.center, right_wire)
        self.left.close()
        self.right.close()
        report = issue_comparison(self.center, second_id, first_id)
        readback = read_comparison(self.center, report.report_id)
        self.assertEqual(report.rows[0].zero_point, F(1, 2))
        self.assertEqual(report.receipt.acceptance_ids, (first_id, second_id))
        self.assertEqual(tuple(item.wire for item in readback.summaries), (first_body, right_wire))

    def test_bad_wire(self):
        valid = json.loads(self.wire)
        missing = dict(valid)
        del missing['zero_point']
        invalid = [None, [], '', '[]', '{', json.dumps(missing), '{"version":1,' + self.wire[1:]]
        for field, value in (
            ('extra', 1), ('version', 2), ('version', True), ('round_id', ''),
            ('bench_id', 'outside'), ('bench_order', ['A', 'A']), ('bench_order', 'BA'),
            ('bench_order', ['B', None]), ('row_count', 0), ('row_count', True),
            ('local_report_id', 0), ('local_report_id', 2**63), ('zero_point', '1/0'),
            ('zero_point', None), ('zero_point', 0.5), ('residual_ss', '-1/2'),
        ):
            invalid.append(json.dumps({**valid, field: value}))
        for wire in invalid:
            with self.subTest(wire=wire), self.assertRaises(ValueError):
                accept_summary(self.center, wire)
        self.assertEqual(counts(self.center, 'accepted_summaries'), (0,))

    def test_unknown_local_report(self):
        with self.assertRaises(KeyError):
            issue_summary(self.left, 999)
