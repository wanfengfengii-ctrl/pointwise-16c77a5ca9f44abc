"""Center selection, mismatch, version mixing, range and rollback rules."""
import json
import sqlite3

from exchange.accept import accept_isolation_evidence, accept_summary
from exchange.issue import issue_isolation_evidence, issue_summary
from protocol.rounds import register_round
from review.publish import issue_comparison, issue_isolation
from review.readback import read_isolation
from review.register import initialize_isolation_store
from tests.isolation_support import IsolationCase


def issue_pair(testcase, *, round_id='round-1', left_rows=None, right_rows=None):
    left_rows = [('a', 0), ('b', 2)] if left_rows is None else left_rows
    right_rows = [('p', 2), ('q', 3)] if right_rows is None else right_rows
    center = testcase.open_center()
    left = testcase.open_site('left')
    right = testcase.open_site('right')
    testcase.register(left, round_id=round_id)
    testcase.register(right, round_id=round_id)
    _, left_freeze = testcase.frozen(left, round_id, 'B', left_rows)
    _, right_freeze = testcase.frozen(right, round_id, 'A', right_rows)
    left_id = accept_isolation_evidence(center, issue_isolation_evidence(left, left_freeze))
    right_id = accept_isolation_evidence(center, issue_isolation_evidence(right, right_freeze))
    return center, left, right, left_id, right_id


class IsolationReviewTests(IsolationCase):
    def test_slot_order_and_reversed_ids(self):
        center, left, right, left_id, right_id = issue_pair(self)
        left.close()
        right.close()
        forward = issue_isolation(center, left_id, right_id)
        reversed_report = issue_isolation(center, right_id, left_id)
        for report in (forward, reversed_report):
            self.assertEqual([source['bench_id'] for source in report['sources']], ['B', 'A'])
            self.assertEqual(report['receipt']['acceptance_ids'], [left_id, right_id])
        self.assertNotEqual(forward['report_id'], reversed_report['report_id'])

    def test_mismatched_round_bench_order_and_reference_order(self):
        center, left, right, left_id, right_id = issue_pair(self)
        # Different round.
        other_site = self.open_site('other-round-site')
        self.register(other_site, round_id='round-2')
        _, other_freeze = self.frozen(other_site, 'round-2', 'B', [('a', 0), ('b', 2)])
        other_round_id = accept_isolation_evidence(center, issue_isolation_evidence(other_site, other_freeze))
        # Different work order slot arrangement (same bench names, swapped).
        swapped_site = self.open_site('swapped')
        swapped_benches = (
            ('A', (('a', (('X', 1), ('Y', -1))), ('b', (('X', 1),)))),
            ('B', (('p', (('X', 1),)), ('q', (('Y', 1),)))),
        )
        self.register(swapped_site, round_id='swapped-round', benches=swapped_benches)
        _, swapped_freeze = self.frozen(swapped_site, 'swapped-round', 'A', [('a', 0), ('b', 2)])
        swapped_id = accept_isolation_evidence(center, issue_isolation_evidence(swapped_site, swapped_freeze))
        # Different reference order (same names, reversed).
        reordered_site = self.open_site('reordered')
        self.register(reordered_site, references=(('Y', 3), ('X', 2)))
        _, reordered_freeze = self.frozen(reordered_site, 'round-1', 'B', [('a', 0), ('b', 2)])
        reordered_id = accept_isolation_evidence(center, issue_isolation_evidence(reordered_site, reordered_freeze))
        # A second evidence from the same bench (a later revision number)
        # is accepted on its own, but selecting two same-bench pieces fails.
        duplicate_site = self.open_site('duplicate')
        self.register(duplicate_site)
        first_rev, _ = self.frozen(duplicate_site, 'round-1', 'B', [('a', 0), ('b', 2)])
        _, duplicate_freeze = self.frozen(
            duplicate_site, 'round-1', 'B', [('a', 1), ('b', 2)], corrects=first_rev)
        duplicate_id = accept_isolation_evidence(center, issue_isolation_evidence(duplicate_site, duplicate_freeze))
        for bad_id in (other_round_id, swapped_id, reordered_id, duplicate_id):
            with self.subTest(bad_id=bad_id):
                # Every bad piece shares the left B slot's role; pair it with
                # the valid B piece so round/slot/bench mismatches surface.
                with self.assertRaises(ValueError):
                    issue_isolation(center, left_id, bad_id)
        with self.assertRaises(ValueError):
            issue_isolation(center, right_id, right_id)

    def test_mixed_versions_raise_value_error(self):
        center, left, right, left_id, right_id = issue_pair(self)
        # A V1 acceptance id is never a valid V2 selection.
        from fit.local_reports import issue_local
        from intake.freeze import freeze_revision
        revision, _ = self.frozen(right, 'round-1', 'A', [('p', 2), ('q', 3)])
        v1_id = accept_summary(center, issue_summary(right, issue_local(right, freeze_revision(right, revision)).report_id))
        with self.assertRaises(ValueError):
            issue_isolation(center, left_id, f'v2:{v1_id}')
        with self.assertRaises(ValueError):
            issue_isolation(center, left_id, v1_id)
        # And V2 ids cannot drive the V1 comparison entry point: a string id is
        # not a V1 integer acceptance number, so it surfaces as a KeyError.
        with self.assertRaises(KeyError):
            issue_comparison(center, v1_id, left_id)

    def test_unknown_ids_are_key_errors(self):
        center, left, right, left_id, right_id = issue_pair(self)
        with self.assertRaises(KeyError):
            issue_isolation(center, left_id, 'v2:999')
        with self.assertRaises(KeyError):
            read_isolation(center, 999)
        with self.assertRaises(ValueError):
            issue_isolation(center, left_id, 'v2:0')

    def test_rollback_on_write_failure_and_retry(self):
        center, left, right, left_id, right_id = issue_pair(self)
        left.close()
        right.close()
        center.execute('''
            CREATE TEMP TRIGGER reject_isolation_receipt BEFORE INSERT ON isolation_receipts
            BEGIN SELECT RAISE(ABORT, 'isolation receipt fixture'); END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'isolation receipt fixture'):
            issue_isolation(center, right_id, left_id)
        self.assertFalse(center.in_transaction)
        counts = tuple(
            center.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
            for table in ('isolation_reports', 'isolation_sources', 'isolation_receipts')
        )
        self.assertEqual(counts, (0, 0, 0))
        # The accepted evidence is untouched and the same inputs now succeed.
        center.execute('DROP TRIGGER reject_isolation_receipt')
        report = issue_isolation(center, right_id, left_id)
        self.assertEqual(read_isolation(center, report['report_id']), report)

    def test_reinitialize_keeps_history(self):
        center, left, right, left_id, right_id = issue_pair(self)
        report = issue_isolation(center, left_id, right_id)
        initialize_isolation_store(center)
        self.assertEqual(read_isolation(center, report['report_id']), report)


class ReferenceRangeTests(IsolationCase):
    def _round(self, db, count):
        names = [f'R{i}' for i in range(count)]
        references = tuple((name, index + 1) for index, name in enumerate(names))
        bench_rows = (
            ('B', tuple((f'b{index}', ((name, 1),)) for index, name in enumerate(names))),
            ('A', (('a', ((names[0], 1),)),)),
        )
        self.register(db, references=references, benches=bench_rows)
        return names, bench_rows

    def test_one_to_eight_references_issue_and_review(self):
        for count in (1, 8):
            with self.subTest(count=count):
                center = self.open_center()
                site = self.open_site(f'site-{count}')
                names, bench_rows = self._round(site, count)
                readings = [(f'b{index}', index + 1) for index in range(count)]
                _, freeze_id = self.frozen(site, 'round-1', 'B', readings)
                wire = issue_isolation_evidence(site, freeze_id)
                acceptance_id = accept_isolation_evidence(center, wire)
                other = self.open_site(f'other-{count}')
                self._round(other, count)
                _, other_freeze = self.frozen(other, 'round-1', 'A', [('a', 0)])
                other_id = accept_isolation_evidence(center, issue_isolation_evidence(other, other_freeze))
                report = issue_isolation(center, acceptance_id, other_id)
                self.assertEqual(report['reference_order'], names)
                self.assertIn(report['status'], ('ok', 'impossible'))

    def test_nine_references_rejected_at_issue_and_acceptance(self):
        site = self.open_site('too-many')
        names, _ = self._round(site, 9)
        _, freeze_id = self.frozen(site, 'round-1', 'B', [(f'b{index}', 1) for index in range(9)])
        with self.assertRaises(ValueError):
            issue_isolation_evidence(site, freeze_id)
        center = self.open_center()
        payload = {
            'version': 2, 'round_id': 'round-1', 'bench_id': 'B', 'revision_id': 1,
            'bench_order': ['B', 'A'], 'reference_order': names,
            'relation': {'kind': 'full'},
        }
        with self.assertRaises(ValueError):
            accept_isolation_evidence(center, json.dumps(payload))

    def test_eight_reference_hand_computed_joint(self):
        # R0..R7. B rows b0,b1 share the R0 sensitivity (their difference is
        # 0 = 0) and b2 uses R3, giving R3 - R0 = 0. A rows a(R0), c(R1)
        # give R0 - R1 = 1. A minimum explanation isolates R0 alone, so the
        # minimum count is one with no universally required reference.
        from fractions import Fraction as F
        from protocol.rounds import get_round

        names = [f'R{index}' for index in range(8)]
        references = tuple((name, index + 1) for index, name in enumerate(names))
        benches = (
            ('B', (
                ('b0', (('R0', 1),)), ('b1', (('R0', 1),)), ('b2', (('R3', 1),)),
            )),
            ('A', (('a', (('R0', 1),)), ('c', (('R1', 1),)))),
        )
        target_residuals = {
            'B': {'b0': F(1), 'b1': F(1), 'b2': F(0)},
            'A': {'a': F(1), 'c': F(0)},
        }
        center = self.open_center()
        acceptance_ids = []
        for bench in ('B', 'A'):
            site = self.open_site(f'hand-{bench}')
            register_round(site, 'r8', references, benches)
            _, nominals = get_round(site, 'r8').bench(bench)
            nominal = {line.row_name: line.value for line in nominals}
            readings = [
                (row, nominal[row] + target_residuals[bench][row])
                for row in target_residuals[bench]
            ]
            _, freeze_id = self.frozen(site, 'r8', bench, readings)
            acceptance_ids.append(
                accept_isolation_evidence(center, issue_isolation_evidence(site, freeze_id)))
        report = issue_isolation(center, *acceptance_ids)
        self.assertEqual(len(report['reference_order']), 8)
        self.assertEqual(report['status'], 'ok')
        # Only the R0 singleton is feasible at size one, so R0 is present in
        # every minimum explanation.
        self.assertEqual(report['minimum_count'], 1)
        self.assertEqual(report['required_references'], ['R0'])
        self.assertEqual(read_isolation(center, report['report_id']), report)
