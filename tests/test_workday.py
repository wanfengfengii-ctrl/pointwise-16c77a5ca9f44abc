import sqlite3
from fractions import Fraction as F

from exchange.accept import accept_summary
from exchange.catalog import get_accepted_summary
from exchange.issue import issue_summary
from fit.local_reports import get_local_report
from intake.freeze import get_frozen_revision
from intake.measurements import record_readings
from intake.revisions import get_revision
from protocol.rounds import get_round
from review.publish import issue_comparison
from review.readback import read_comparison
from tests.support import (
    CORRECTION, LEFT, LEFT_READINGS, RIGHT, RIGHT_READINGS, ROUND,
    CalibrationCase, counts, register_example, report_for,
)


class WorkdayTests(CalibrationCase):
    def test_reinitialize_with_correction_and_signed_reports(self):
        left, right = self.two_sites()
        center = self.open_center()
        initial = record_readings(left, ROUND, LEFT, LEFT_READINGS)
        prior_local = report_for(left, initial)
        prior_wire = issue_summary(left, prior_local.report_id)
        first_id = accept_summary(center, prior_wire)
        right_revision = record_readings(right, ROUND, RIGHT, RIGHT_READINGS)
        right_local = report_for(right, right_revision)
        right_wire = issue_summary(right, right_local.report_id)
        right_id = accept_summary(center, right_wire)
        left.close()
        right.close()
        prior = issue_comparison(center, right_id, first_id)

        left = self.open_site(LEFT)
        corrected = record_readings(left, ROUND, LEFT, CORRECTION, corrects=initial)
        register_example(left, 'shift-2', x=7)
        corrected_local = report_for(left, corrected)
        corrected_wire = issue_summary(left, corrected_local.report_id)
        corrected_id = accept_summary(center, corrected_wire)
        left.close()
        center.execute('''
            CREATE TEMP TRIGGER reject_corrected_receipt BEFORE INSERT ON comparison_receipts
            BEGIN SELECT RAISE(ABORT, 'corrected receipt fixture'); END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'corrected receipt fixture'):
            issue_comparison(center, right_id, corrected_id)
        self.assertEqual(counts(center, 'comparison_reports', 'comparison_rows', 'comparison_receipts'), (1, 2, 1))
        center.close()
        center = self.open_center()
        current = issue_comparison(center, right_id, corrected_id)
        center.close()

        left = self.open_site(LEFT)
        center = self.open_center()
        self.assertEqual(get_round(left, ROUND).bench(LEFT)[1][0].value, F(-1))
        self.assertEqual(get_round(left, 'shift-2').bench(LEFT)[1][0].value, F(4))
        self.assertEqual(get_revision(left, corrected).parent_id, initial)
        self.assertEqual(get_frozen_revision(left, prior_local.freeze_id).revision.revision_id, initial)
        self.assertEqual(get_local_report(left, prior_local.report_id), prior_local)
        self.assertEqual(get_local_report(left, corrected_local.report_id), corrected_local)
        self.assertEqual(issue_summary(left, corrected_local.report_id), corrected_wire)
        self.assertEqual(accept_summary(center, corrected_wire), corrected_id)
        self.assertEqual(get_accepted_summary(center, first_id).wire, prior_wire)
        for report, source, wire, zero, squares in (
            (prior, first_id, prior_wire, F(1, 2), F(1, 2)),
            (current, corrected_id, corrected_wire, F(3, 2), F(9, 2)),
        ):
            with self.subTest(report=report.report_id):
                pickup = read_comparison(center, report.report_id)
                self.assertEqual(pickup.report, report)
                self.assertEqual(pickup.report.receipt.acceptance_ids, (source, right_id))
                self.assertEqual((pickup.report.rows[0].zero_point, pickup.report.rows[0].residual_ss), (zero, squares))
                self.assertEqual(tuple(item.wire for item in pickup.summaries), (wire, right_wire))
        self.assertEqual(counts(center, 'comparison_reports', 'comparison_rows', 'comparison_receipts'), (2, 4, 2))

        following = record_readings(left, ROUND, LEFT, [('a', 1)], corrects=corrected)
        self.assertEqual(get_revision(left, following).parent_id, corrected)
        later_wire = issue_summary(left, report_for(left, following).report_id)
        later_id = accept_summary(center, later_wire)
        left.close()
        later = issue_comparison(center, later_id, right_id)
        self.assertEqual(later.rows[0].zero_point, F(2))
        self.assertEqual(later.receipt.acceptance_ids, (later_id, right_id))
        self.assertEqual(read_comparison(center, prior.report_id).report, prior)
