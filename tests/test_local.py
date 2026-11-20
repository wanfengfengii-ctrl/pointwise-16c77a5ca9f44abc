import sqlite3
from fractions import Fraction as F

from fit.local_reports import get_local_report, issue_local
from fit.observations import load_observations
from intake.freeze import freeze_revision, get_frozen_revision
from intake.measurements import record_readings
from intake.revisions import get_revision
from tests.support import (
    CORRECTION, LEFT, LEFT_READINGS, RIGHT, RIGHT_READINGS, ROUND,
    CalibrationCase, counts, register_example, report_for,
)


class LocalTests(CalibrationCase):
    def setUp(self):
        super().setUp()
        self.site = self.open_site(LEFT)
        register_example(self.site)

    def record_left(self, rows=LEFT_READINGS, *, corrects=None):
        return record_readings(self.site, ROUND, LEFT, rows, corrects=corrects)

    def test_local_fit(self):
        revision = self.record_left()
        report = report_for(self.site, revision)
        self.assertEqual((report.round_id, report.bench_id, report.revision_id), (ROUND, LEFT, revision))
        self.assertEqual(report.zero_point, F(1, 2))
        self.assertEqual((report.statistics.row_count, report.statistics.residual_ss), (2, F(1, 2)))
        self.assertEqual([(row.row_name, row.deviation) for row in report.statistics.deviations], [
            ('a', F(1, 2)), ('b', F(-1, 2))
        ])
        self.assertEqual(get_local_report(self.site, report.report_id), report)

    def test_reordered_rows(self):
        revision = self.record_left()
        rows = get_revision(self.site, revision).rows
        self.assertEqual([(row.row_name, row.position, row.value) for row in rows], [
            ('a', 0, F(0)), ('b', 1, F(2))
        ])
        batch = load_observations(self.site, freeze_revision(self.site, revision))
        self.assertEqual([(row.row_name, row.nominal_residual) for row in batch.rows], [('a', F(1)), ('b', F(0))])

    def test_line_mismatch(self):
        for bad in (
            [('unused', 1)], [('a', 0), ('a', 1)], [('a', None)], [('a', False)], [('a', 0.0)], [('a', '1/0')],
        ):
            with self.subTest(rows=bad), self.assertRaises(ValueError):
                self.record_left(bad)
        with self.assertRaises(ValueError):
            record_readings(self.site, ROUND, 'another-bench', LEFT_READINGS)
        with self.assertRaises(ValueError):
            record_readings(self.site, ROUND, RIGHT, [('half', 0)])
        with self.assertRaises(KeyError):
            record_readings(self.site, 'unknown-round', LEFT, LEFT_READINGS)
        self.assertEqual(counts(self.site, 'reading_revisions', 'reading_rows'), (0, 0))

    def test_empty_revision(self):
        revision = self.record_left([])
        self.assertEqual(get_revision(self.site, revision).rows, ())
        with self.assertRaises(ValueError):
            freeze_revision(self.site, revision)
        self.assertEqual(counts(self.site, 'reading_revisions', 'frozen_revisions'), (1, 0))

    def test_single_row(self):
        report = report_for(self.site, self.record_left([('b', '0/3')]))
        self.assertEqual(report.zero_point, F(-2))
        self.assertEqual((report.statistics.row_count, report.statistics.residual_ss), (1, F(0)))
        self.assertEqual([(row.row_name, row.deviation) for row in report.statistics.deviations], [('b', F(0))])

    def test_correction_lineage(self):
        first = self.record_left()
        frozen = freeze_revision(self.site, first)
        next_revision = self.record_left(CORRECTION, corrects=first)
        self.assertNotEqual(first, next_revision)
        self.assertEqual(get_revision(self.site, next_revision).parent_id, first)
        self.assertIsNone(get_revision(self.site, first).parent_id)
        self.assertEqual([row.value for row in get_revision(self.site, next_revision).rows], [F(2), F(2)])
        self.assertEqual([row.value for row in get_frozen_revision(self.site, frozen).revision.rows], [F(0), F(2)])
        with self.assertRaises(ValueError):
            record_readings(self.site, ROUND, RIGHT, RIGHT_READINGS, corrects=first)
        register_example(self.site, 'other-round')
        with self.assertRaises(ValueError):
            record_readings(self.site, 'other-round', LEFT, CORRECTION, corrects=first)
        self.assertEqual(counts(self.site, 'reading_revisions', 'reading_rows'), (2, 4))

    def test_frozen_version(self):
        first = self.record_left()
        updated = self.record_left(CORRECTION, corrects=first)
        older_frozen = freeze_revision(self.site, first)
        newer_frozen = freeze_revision(self.site, updated)
        old_report = issue_local(self.site, older_frozen)
        new_report = issue_local(self.site, newer_frozen)
        self.assertEqual((old_report.revision_id, old_report.zero_point, old_report.statistics.residual_ss),
                         (first, F(1, 2), F(1, 2)))
        self.assertEqual((new_report.revision_id, new_report.zero_point, new_report.statistics.residual_ss),
                         (updated, F(3, 2), F(9, 2)))
        self.assertEqual(get_frozen_revision(self.site, older_frozen).revision.revision_id, first)

    def test_missing_revision(self):
        with self.assertRaises(KeyError):
            freeze_revision(self.site, 999)
        self.assertEqual(counts(self.site, 'frozen_revisions'), (0,))

    def test_unknown_correction(self):
        with self.assertRaises(KeyError):
            self.record_left(CORRECTION, corrects=999)
        self.assertEqual(counts(self.site, 'reading_revisions', 'reading_rows'), (0, 0))

    def test_unknown_freeze(self):
        with self.assertRaises(KeyError):
            issue_local(self.site, 999)
        self.assertEqual(counts(self.site, 'local_reports', 'local_deviations'), (0, 0))

    def test_failed_local_write(self):
        frozen = freeze_revision(self.site, self.record_left())
        self.site.execute('''
            CREATE TEMP TRIGGER reject_second_deviation
            BEFORE INSERT ON local_deviations WHEN NEW.position = 1
            BEGIN SELECT RAISE(ABORT, 'local detail fixture'); END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'local detail fixture'):
            issue_local(self.site, frozen)
        self.assertEqual(counts(self.site, 'local_reports', 'local_deviations', 'frozen_revisions'), (0, 0, 1))
        with self.assertRaises(KeyError):
            get_local_report(self.site, 1)
        self.site.execute('DROP TRIGGER reject_second_deviation')
        report = issue_local(self.site, frozen)
        self.assertEqual(counts(self.site, 'local_reports', 'local_deviations'), (1, 2))
        self.assertEqual(get_local_report(self.site, report.report_id), report)
