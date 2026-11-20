"""Full delivery verification.

Runs, in one process so any failure yields a non-zero exit:

1. the complete unittest suite (all V1 regressions plus the V2 tests covering
   freezing, reverse-order selection, sample results, pickup, mismatches,
   mixed versions and write-failure retry);
2. the original V1 sample statistics check from check_isolation_inputs.py;
3. an end-to-end V2 check over every SAMPLE case, asserting the expected
   status, minimum count, required references and stored pickup.
"""
import sqlite3
import unittest
from contextlib import closing

from check_isolation_inputs import SAMPLE, check as check_v1_sample
from demo import initialize_site
from exchange.accept import accept_isolation_evidence
from exchange.catalog import initialize_acceptance_store
from exchange.issue import issue_isolation_evidence
from intake.freeze import freeze_revision
from intake.measurements import record_readings
from protocol.rounds import register_round
from review.publish import issue_isolation
from review.readback import read_isolation
from review.register import initialize_comparison_store, initialize_isolation_store


def run_unittest_suite() -> bool:
    suite = unittest.defaultTestLoader.discover('tests', top_level_dir='.')
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    for status, failed_cases in (
        ('FAIL', (test for test, _ in result.failures)),
        ('ERROR', (test for test, _ in result.errors)),
        ('UNEXPECTED_SUCCESS', result.unexpectedSuccesses),
    ):
        for test in failed_cases:
            print(f'{status} {test.id()}')
    return result.testsRun > 0 and result.wasSuccessful()


def check_v2_sample() -> None:
    order = tuple(bench for bench, _ in SAMPLE['benches'])
    with closing(sqlite3.connect(':memory:')) as center:
        initialize_acceptance_store(center)
        initialize_comparison_store(center)
        initialize_isolation_store(center)
        accepted = {}
        for bench in order:
            with closing(sqlite3.connect(':memory:')) as site:
                initialize_site(site)
                register_round(site, SAMPLE['round_id'], SAMPLE['references'], SAMPLE['benches'])
                parent = None
                for name, readings in SAMPLE['revisions'][bench].items():
                    revision = record_readings(
                        site, SAMPLE['round_id'], bench, readings, corrects=parent)
                    if parent is None:
                        parent = revision
                    wire = issue_isolation_evidence(site, freeze_revision(site, revision))
                    accepted[bench, name] = (accept_isolation_evidence(center, wire), wire)
        for case in SAMPLE['cases']:
            sources = [accepted[key][0] for key in zip(order, case['select'], strict=True)]
            wires = [accepted[key][1] for key in zip(order, case['select'], strict=True)]
            report = issue_isolation(center, *reversed(sources))
            actual = [report['status'], report['minimum_count'], report['required_references']]
            if actual != case['expected']:
                raise AssertionError(f"V2 sample case {case['name']}: {actual} != {case['expected']}")
            pickup = read_isolation(center, report['report_id'])
            if pickup != report:
                raise AssertionError(f"V2 sample case {case['name']}: pickup lost stored values")
            if pickup['receipt']['acceptance_ids'] != sources:
                raise AssertionError(f"V2 sample case {case['name']}: receipt order mismatch")
            if [source['wire'] for source in pickup['sources']] != wires:
                raise AssertionError(f"V2 sample case {case['name']}: source wires not preserved")
            if [source['bench_id'] for source in report['sources']] == list(reversed(order)):
                raise AssertionError(f"V2 sample case {case['name']}: sources not in work order slots")
    print(f"V2 SAMPLE cases verified: {len(SAMPLE['cases'])}")


def main() -> int:
    if not run_unittest_suite():
        return 1
    check_v1_sample(SAMPLE)
    check_v2_sample()
    print('ISOLATION VERIFY RESULT=PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
