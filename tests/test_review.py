import json
import sqlite3
from fractions import Fraction as F

from exchange.accept import accept_summary
from exchange.issue import issue_summary
from protocol.rounds import register_round
from review.publish import issue_comparison
from review.readback import read_comparison
from tests.support import (
    CORRECTION, LEFT, LEFT_READINGS, RIGHT, RIGHT_READINGS, ROUND,
    CalibrationCase, counts, example_benches, make_summary, register_example,
)


class ReviewTests(CalibrationCase):
    def setUp(self):
        super().setUp()
        self.left, self.right = self.two_sites()
        self.center = self.open_center()
        self.original_revision, self.left_wire = make_summary(self.left, LEFT, LEFT_READINGS)
        _, self.right_wire = make_summary(self.right, RIGHT, RIGHT_READINGS)
        self.right_id = accept_summary(self.center, self.right_wire)
        self.left_id = accept_summary(self.center, self.left_wire)

    def close_sites(self):
        self.left.close()
        self.right.close()

    def check_pickup(self, report, left_id, left_wire, zero=F(1, 2), squares=F(1, 2)):
        pickup = read_comparison(self.center, report.report_id)
        self.assertEqual(pickup.report, report)
        self.assertEqual(report.round_id, ROUND)
        self.assertEqual(report.receipt.report_id, report.report_id)
        self.assertEqual(report.receipt.acceptance_ids, (left_id, self.right_id))
        self.assertEqual([
            (row.bench_id, row.acceptance_id, row.zero_point, row.row_count, row.residual_ss)
            for row in pickup.report.rows
        ], [
            (LEFT, left_id, zero, 2, squares),
            (RIGHT, self.right_id, F(4), 1, F(0)),
        ])
        self.assertEqual(tuple(item.acceptance_id for item in pickup.summaries), (left_id, self.right_id))
        self.assertEqual(tuple(item.wire for item in pickup.summaries), (left_wire, self.right_wire))

    def test_closed_sites(self):
        self.close_sites()
        report = issue_comparison(self.center, self.right_id, self.left_id)
        self.check_pickup(report, self.left_id, self.left_wire)

    def test_v1_payload(self):
        self.assertEqual(json.loads(self.left_wire), {
            'version': 1, 'round_id': ROUND, 'bench_id': LEFT, 'local_report_id': 1,
            'bench_order': [LEFT, RIGHT], 'zero_point': '1/2', 'row_count': 2, 'residual_ss': '1/2',
        })
        self.assertEqual(issue_summary(self.left, 1), self.left_wire)

    def test_bad_selection(self):
        _, alternate_left = make_summary(self.left, LEFT, LEFT_READINGS)
        alternate_id = accept_summary(self.center, alternate_left)
        register_example(self.right, 'other-round')
        _, different_round = make_summary(self.right, RIGHT, RIGHT_READINGS, round_id='other-round')
        different_round_id = accept_summary(self.center, different_round)
        alternate_site = self.open_site('different-work-order')
        register_round(alternate_site, ROUND, [('X', 2), ('Y', 3)], tuple(reversed(example_benches())))
        # Use a local report number absent from the center's A issuer namespace.
        make_summary(alternate_site, RIGHT, RIGHT_READINGS)
        make_summary(alternate_site, RIGHT, RIGHT_READINGS)
        _, different_order = make_summary(alternate_site, RIGHT, RIGHT_READINGS)
        different_order_id = accept_summary(self.center, different_order)
        self.close_sites()
        alternate_site.close()
        for other in (self.left_id, alternate_id, different_round_id, different_order_id):
            with self.subTest(other=other), self.assertRaises(ValueError):
                issue_comparison(self.center, self.left_id, other)
        with self.assertRaises(KeyError):
            issue_comparison(self.center, self.left_id, 999)
        self.assertEqual(counts(self.center, 'comparison_reports', 'comparison_rows', 'comparison_receipts'), (0, 0, 0))

    def test_rollback(self):
        self.close_sites()
        self.center.execute('''
            CREATE TEMP TRIGGER reject_comparison_receipt BEFORE INSERT ON comparison_receipts
            BEGIN SELECT RAISE(ABORT, 'receipt fixture'); END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'receipt fixture'):
            issue_comparison(self.center, self.right_id, self.left_id)
        self.assertFalse(self.center.in_transaction)
        self.assertEqual(
            counts(self.center, 'comparison_reports', 'comparison_rows', 'comparison_receipts', 'accepted_summaries'),
            (0, 0, 0, 2),
        )
        with self.assertRaises(KeyError):
            read_comparison(self.center, 1)
        self.center.execute('DROP TRIGGER reject_comparison_receipt')
        report = issue_comparison(self.center, self.right_id, self.left_id)
        self.assertEqual(counts(self.center, 'comparison_reports', 'comparison_rows', 'comparison_receipts'), (1, 2, 1))
        self.center.close()
        self.center = self.open_center()
        self.check_pickup(report, self.left_id, self.left_wire)

    def test_historical(self):
        self.close_sites()
        original = issue_comparison(self.center, self.right_id, self.left_id)
        self.check_pickup(original, self.left_id, self.left_wire)
        self.left = self.open_site(LEFT)
        _, corrected_wire = make_summary(self.left, LEFT, CORRECTION, corrects=self.original_revision)
        corrected_id = accept_summary(self.center, corrected_wire)
        self.left.close()
        corrected = issue_comparison(self.center, self.right_id, corrected_id)
        self.assertNotEqual(original.report_id, corrected.report_id)
        self.assertNotEqual(original.receipt.receipt_id, corrected.receipt.receipt_id)
        self.center.close()
        self.center = self.open_center()
        self.check_pickup(original, self.left_id, self.left_wire)
        self.check_pickup(corrected, corrected_id, corrected_wire, F(3, 2), F(9, 2))

    def test_unknown_report(self):
        with self.assertRaises(KeyError):
            read_comparison(self.center, 999)
        self.assertEqual(counts(self.center, 'comparison_reports', 'comparison_receipts'), (0, 0))
