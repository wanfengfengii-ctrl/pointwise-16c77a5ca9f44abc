"""V2 isolation demonstration.

Shows, on independent temporary SQLite stores:

1. ``disconnected_issue`` - both site stores are closed before the center
   issues the minimum isolation report, proving the center works only from
   the two accepted V2 pieces;
2. ``reopen_pickup`` - a source revision is corrected at the site and a new
   report is issued, after which the center is reopened and the original
   report number returns its stored value, receipt and the two original
   wires, while the corrected report keeps its own number.
"""
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from check_isolation_inputs import SAMPLE
from exchange.accept import accept_isolation_evidence
from exchange.catalog import initialize_acceptance_store
from exchange.issue import issue_isolation_evidence
from intake.freeze import freeze_revision
from intake.measurements import record_readings
from protocol.rounds import register_round
from review.publish import issue_isolation
from review.readback import read_isolation
from review.register import initialize_comparison_store, initialize_isolation_store
from tests.isolation_support import initialize_site


def print_scenario(case_id, payload, oracle):
    print('POINTWISE_ISOLATION ' + json.dumps(
        {'case_id': case_id, **payload}, ensure_ascii=False, sort_keys=True,
    ))
    print('  说明：' + oracle)


def _issue(site, center, round_id, bench, readings, parent):
    revision = record_readings(site, round_id, bench, readings, corrects=parent)
    wire = issue_isolation_evidence(site, freeze_revision(site, revision))
    acceptance_id = accept_isolation_evidence(center, wire)
    return revision, wire, acceptance_id


def main():
    round_id = SAMPLE['round_id']
    references = SAMPLE['references']
    benches = SAMPLE['benches']
    bench_order = [bench for bench, _ in benches]
    with TemporaryDirectory() as workspace:
        folder = Path(workspace)
        site_paths = {bench: folder / f'{bench}.sqlite' for bench in bench_order}
        center_path = folder / 'center.sqlite'

        with closing(sqlite3.connect(center_path)) as center:
            initialize_acceptance_store(center)
            initialize_comparison_store(center)
            initialize_isolation_store(center)
            first_wires = {}
            first_ids = {}
            first_revisions = {}
            for bench in bench_order:
                with closing(sqlite3.connect(site_paths[bench])) as site:
                    initialize_site(site)
                    register_round(site, round_id, references, benches)
                    selection = 'initial' if bench == 'B' else 'equal'
                    revision, wire, acceptance_id = _issue(
                        site, center, round_id, bench,
                        SAMPLE['revisions'][bench][selection], None,
                    )
                    first_wires[bench] = wire
                    first_revisions[bench] = revision
                    first_ids[bench] = acceptance_id
            # Both site stores are now closed.  The center issues offline.
            ordered_ids = [first_ids[bench] for bench in bench_order]
            first_report = issue_isolation(center, *reversed(ordered_ids))
            assert first_report['sources'][0]['wire'] == first_wires['B']
            assert first_report['sources'][1]['wire'] == first_wires['A']
            assert first_report['receipt']['acceptance_ids'] == ordered_ids
            print_scenario(
                'disconnected_issue',
                {
                    'acceptance_ids': ordered_ids,
                    'status': first_report['status'],
                    'minimum_count': first_report['minimum_count'],
                    'required_references': first_report['required_references'],
                    'sites_closed': True,
                },
                '两台站库关闭后，中心仅凭两份 V2 件核定；联合约束 X+Y=1 与 X−Y=0 要求两件标样均隔离。',
            )

            # Correct the B source revision; the historical report is untouched.
            with closing(sqlite3.connect(site_paths['B'])) as site:
                initialize_site(site)
                corrected_revision, corrected_wire, corrected_id = _issue(
                    site, center, round_id, 'B',
                    SAMPLE['revisions']['B']['shifted'], first_revisions['B'],
                )
            corrected_ids = [corrected_id, first_ids['A']]
            corrected_report = issue_isolation(center, *reversed(corrected_ids))
            print_scenario(
                'corrected_reissue',
                {
                    'report_ids': [first_report['report_id'], corrected_report['report_id']],
                    'corrected_revision': corrected_revision,
                    'first_status': first_report['status'],
                    'corrected_status': corrected_report['status'],
                    'corrected_minimum_count': corrected_report['minimum_count'],
                },
                'B 台勘误另发新报告，旧报告号与回执保持不变。',
            )

        # Reopen the center with no site available and read by the old numbers.
        with closing(sqlite3.connect(center_path)) as reopened:
            initialize_acceptance_store(reopened)
            initialize_comparison_store(reopened)
            initialize_isolation_store(reopened)
            old_pickup = read_isolation(reopened, first_report['report_id'])
            new_pickup = read_isolation(reopened, corrected_report['report_id'])
            assert old_pickup == first_report
            assert new_pickup == corrected_report
            assert [source['wire'] for source in old_pickup['sources']] == [
                first_wires['B'], first_wires['A'],
            ]
            assert old_pickup['sources'][0]['revision_id'] == first_revisions['B']
            print_scenario(
                'reopen_pickup',
                {
                    'old_report_id': first_report['report_id'],
                    'old_stored': {
                        'status': old_pickup['status'],
                        'minimum_count': old_pickup['minimum_count'],
                        'required_references': old_pickup['required_references'],
                        'receipt_id': old_pickup['receipt']['receipt_id'],
                        'acceptance_ids': old_pickup['receipt']['acceptance_ids'],
                        'source_revisions': [source['revision_id'] for source in old_pickup['sources']],
                    },
                    'new_report_id': corrected_report['report_id'],
                    'new_stored_revisions': [
                        source['revision_id'] for source in new_pickup['sources']
                    ],
                    'historical_wires_preserved': True,
                },
                '中心重开后按原报告号领取存值、回执与两份原 V2 来件；勘误只影响新号。',
            )


if __name__ == '__main__':
    main()
