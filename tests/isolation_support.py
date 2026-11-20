"""Shared fixtures for V2 isolation tests, independent of the V1 support."""
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from exchange.catalog import initialize_acceptance_store
from fit.local_reports import initialize_local_report_store
from intake.freeze import freeze_revision, initialize_freeze_store
from intake.measurements import record_readings
from intake.revisions import initialize_revision_store
from protocol.rounds import initialize_round_store, register_round
from review.register import initialize_comparison_store, initialize_isolation_store


def initialize_site(db):
    initialize_round_store(db)
    initialize_revision_store(db)
    initialize_freeze_store(db)
    initialize_local_report_store(db)


def initialize_center(db):
    initialize_acceptance_store(db)
    initialize_comparison_store(db)
    initialize_isolation_store(db)


class IsolationCase(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.folder = Path(folder)

    def connect(self, filename):
        db = sqlite3.connect(self.folder / filename)
        self.addCleanup(db.close)
        return db

    def open_site(self, name='site'):
        db = self.connect(f'{name}.sqlite')
        initialize_site(db)
        return db

    def open_center(self):
        db = self.connect('center.sqlite')
        initialize_center(db)
        return db

    def register(self, db, *, round_id='round-1', references=None, benches=None):
        references = references or (('X', 2), ('Y', 3))
        benches = benches or (
            ('B', (('a', (('X', 1), ('Y', -1))), ('b', (('X', 1),)))),
            ('A', (('p', (('X', 1),)), ('p_repeat', (('X', 1),)),
                   ('q', (('Y', 1),)), ('r', (('Y', -1),)))),
        )
        return register_round(db, round_id, references, benches)

    def frozen(self, db, round_id, bench, readings, *, corrects=None):
        revision = record_readings(db, round_id, bench, readings, corrects=corrects)
        return revision, freeze_revision(db, revision)
