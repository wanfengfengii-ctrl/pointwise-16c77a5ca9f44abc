import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from exchange.catalog import initialize_acceptance_store
from exchange.issue import issue_summary
from fit.local_reports import initialize_local_report_store, issue_local
from intake.freeze import freeze_revision, initialize_freeze_store
from intake.measurements import record_readings
from intake.revisions import initialize_revision_store
from protocol.rounds import initialize_round_store, register_round
from review.register import initialize_comparison_store

ROUND = 'shift-1'
LEFT = 'B'
RIGHT = 'A'
LEFT_READINGS = (('b', 2), ('a', 0))
RIGHT_READINGS = (('a', 7),)
CORRECTION = (('b', 2), ('a', 2))


def example_benches():
    return (
        (LEFT, (('a', (('X', 1), ('Y', -1))), ('b', (('X', 1),)),
                ('half', (('X', '1/2'), ('Y', '-1/2'))))),
        (RIGHT, (('a', (('Y', 1),)), ('b', (('X', -1),)))),
    )


def register_example(db, round_id=ROUND, x=2):
    return register_round(db, round_id, (('X', x), ('Y', 3)), example_benches())


def counts(db, *tables):
    return tuple(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in tables)


def report_for(db, revision):
    return issue_local(db, freeze_revision(db, revision))


def make_summary(db, bench, rows, *, round_id=ROUND, corrects=None):
    revision = record_readings(db, round_id, bench, rows, corrects=corrects)
    report = report_for(db, revision)
    return revision, issue_summary(db, report.report_id)


class CalibrationCase(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.folder = Path(folder)

    def _connect(self, filename):
        db = sqlite3.connect(self.folder / filename)
        self.addCleanup(db.close)
        return db

    def open_site(self, bench):
        db = self._connect(f'bench-{bench}.sqlite')
        initialize_round_store(db)
        initialize_revision_store(db)
        initialize_freeze_store(db)
        initialize_local_report_store(db)
        return db

    def open_center(self):
        db = self._connect('center.sqlite')
        initialize_acceptance_store(db)
        initialize_comparison_store(db)
        return db

    def two_sites(self):
        left = self.open_site(LEFT)
        right = self.open_site(RIGHT)
        register_example(left)
        register_example(right)
        return left, right
