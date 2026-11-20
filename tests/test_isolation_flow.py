"""End-to-end V2 isolation flow on the check_isolation_inputs SAMPLE."""
from exchange.accept import accept_isolation_evidence
from exchange.issue import issue_isolation_evidence
from intake.measurements import record_readings
from protocol.rounds import register_round
from review.publish import issue_isolation
from review.readback import read_isolation
from tests.isolation_support import IsolationCase


def build_sample_centers(testcase):
    from check_isolation_inputs import SAMPLE
    center = testcase.open_center()
    order = tuple(bench for bench, _ in SAMPLE['benches'])
    accepted = {}
    for bench in order:
        site = testcase.open_site(f'bench-{bench}')
        register_round(site, SAMPLE['round_id'], SAMPLE['references'], SAMPLE['benches'])
        parent = None
        for name, readings in SAMPLE['revisions'][bench].items():
            revision = record_readings(site, SAMPLE['round_id'], bench, readings, corrects=parent)
            if parent is None:
                parent = revision
            wire = issue_isolation_evidence(site, freeze(site, revision))
            accepted[bench, name] = (accept_isolation_evidence(center, wire), wire)
        site.close()
    return center, order, accepted, SAMPLE


def freeze(db, revision):
    from intake.freeze import freeze_revision
    return freeze_revision(db, revision)


class IsolationFlowTests(IsolationCase):
    def test_sample_cases_and_pickup(self):
        center, order, accepted, sample = build_sample_centers(self)
        for case in sample['cases']:
            with self.subTest(case=case['name']):
                sources = [accepted[key][0] for key in zip(order, case['select'], strict=True)]
                wires = [accepted[key][1] for key in zip(order, case['select'], strict=True)]
                report = issue_isolation(center, *reversed(sources))
                expected_status, expected_count, expected_required = case['expected']
                self.assertEqual(report['status'], expected_status)
                self.assertEqual(report['minimum_count'], expected_count)
                self.assertEqual(report['required_references'], expected_required)
                self.assertEqual(report['reference_order'], ['X', 'Y'])
                self.assertEqual(report['round_id'], sample['round_id'])
                self.assertEqual(
                    [source['acceptance_id'] for source in report['sources']], sources,
                )
                self.assertEqual([source['wire'] for source in report['sources']], wires)
                self.assertEqual(report['receipt']['acceptance_ids'], sources)
                self.assertEqual(report['receipt']['report_id'], report['report_id'])
                self.assertIsInstance(report['receipt']['receipt_id'], int)
                pickup = read_isolation(center, report['report_id'])
                self.assertEqual(pickup, report)

    def test_issue_after_site_close_and_reopen_pickup(self):
        # The center must issue purely from accepted wires, with no site open.
        center, order, accepted, sample = build_sample_centers(self)
        sources = [accepted[key][0] for key in zip(order, ('initial', 'equal'))]
        report = issue_isolation(center, *reversed(sources))
        center.close()
        reopened = self.open_center()
        pickup = read_isolation(reopened, report['report_id'])
        self.assertEqual(pickup, report)
        self.assertEqual(pickup['sources'][0]['bench_id'], 'B')
        self.assertEqual(pickup['sources'][1]['bench_id'], 'A')

    def test_revision_correction_keeps_historical_report(self):
        from check_isolation_inputs import SAMPLE
        center = self.open_center()
        site = self.open_site('bench-B')
        register_round(site, SAMPLE['round_id'], SAMPLE['references'], SAMPLE['benches'])
        first_rev, first_freeze = self.frozen(
            site, SAMPLE['round_id'], 'B', SAMPLE['revisions']['B']['initial'])
        first_wire = issue_isolation_evidence(site, first_freeze)
        first_id = accept_isolation_evidence(center, first_wire)

        other = self.open_site('bench-A')
        register_round(other, SAMPLE['round_id'], SAMPLE['references'], SAMPLE['benches'])
        _, equal_freeze = self.frozen(other, SAMPLE['round_id'], 'A', SAMPLE['revisions']['A']['equal'])
        equal_wire = issue_isolation_evidence(other, equal_freeze)
        equal_id = accept_isolation_evidence(center, equal_wire)
        other.close()

        historical = issue_isolation(center, equal_id, first_id)
        site.close()

        site = self.open_site('bench-B')
        corrected_rev, corrected_freeze = self.frozen(
            site, SAMPLE['round_id'], 'B', SAMPLE['revisions']['B']['shifted'], corrects=first_rev)
        corrected_wire = issue_isolation_evidence(site, corrected_freeze)
        corrected_id = accept_isolation_evidence(center, corrected_wire)
        site.close()

        corrected_report = issue_isolation(center, equal_id, corrected_id)
        self.assertNotEqual(historical['report_id'], corrected_report['report_id'])
        self.assertNotEqual(historical['receipt']['receipt_id'], corrected_report['receipt']['receipt_id'])
        pickup = read_isolation(center, historical['report_id'])
        self.assertEqual(pickup, historical)
        self.assertEqual(pickup['sources'][0]['wire'], first_wire)
        self.assertEqual(pickup['sources'][0]['revision_id'], first_rev)
        self.assertEqual(corrected_report['sources'][0]['revision_id'], corrected_rev)
