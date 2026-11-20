import json
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from exchange.accept import accept_summary
from exchange.catalog import initialize_acceptance_store
from exchange.issue import issue_summary
from fit.local_reports import initialize_local_report_store, issue_local
from intake.freeze import freeze_revision, initialize_freeze_store
from intake.measurements import record_readings
from intake.revisions import initialize_revision_store
from protocol.rounds import initialize_round_store, register_round
from review.publish import issue_comparison
from review.readback import read_comparison
from review.register import initialize_comparison_store


def initialize_site(db):
    initialize_round_store(db)
    initialize_revision_store(db)
    initialize_freeze_store(db)
    initialize_local_report_store(db)


def issue_wire(db, revision):
    report = issue_local(db, freeze_revision(db, revision))
    return issue_summary(db, report.report_id)


def display_rows(report):
    return [[row.bench_id, str(row.zero_point), row.row_count, str(row.residual_ss)] for row in report.rows]


def pickup_matches(pickup, report, wires, sources):
    return (pickup.report == report and pickup.report.receipt.report_id == report.report_id
            and pickup.report.receipt.acceptance_ids == tuple(sources)
            and tuple(summary.acceptance_id for summary in pickup.summaries) == tuple(sources)
            and tuple(summary.wire for summary in pickup.summaries) == tuple(wires))


def print_scenario(case_id, inputs, expected, actual, expected_pickup, actual_pickup, code_paths, oracle):
    if actual != expected or actual_pickup != expected_pickup:
        raise AssertionError(f'{case_id}: unexpected signed values or pickup: {actual!r}, {actual_pickup!r}')
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': case_id, 'input': inputs, 'expected': expected, 'actual': actual,
        'downstream_expected': expected_pickup, 'downstream_actual': actual_pickup,
        'code_paths': code_paths, 'oracle': oracle,
    }, ensure_ascii=False, sort_keys=True))


def main():
    samples = Path(__file__).resolve().parent / 'samples'
    work = json.loads((samples / 'work-order.json').read_text(encoding='utf-8'))
    data = json.loads((samples / 'readings.json').read_text(encoding='utf-8'))
    first_bench, second_bench = (entry[0] for entry in work['benches'])
    round_id = work['round_id']
    correction = data['correction']
    with TemporaryDirectory() as workspace:
        folder = Path(workspace)
        site_paths = {first_bench: folder / 'first.sqlite', second_bench: folder / 'second.sqlite'}
        center_path = folder / 'center.sqlite'
        with closing(sqlite3.connect(center_path)) as center:
            initialize_acceptance_store(center)
            initialize_comparison_store(center)
            drafts = {}
            accepted = {}
            for bench in (first_bench, second_bench):
                with closing(sqlite3.connect(site_paths[bench])) as site:
                    initialize_site(site)
                    register_round(site, round_id, work['references'], work['benches'])
                    revision = record_readings(site, round_id, bench, data['first_pass'][bench])
                    wire = issue_wire(site, revision)
                    drafts[bench] = (revision, wire)
                    accepted[bench] = accept_summary(center, wire)
            old_sources = (accepted[first_bench], accepted[second_bench])
            old_wires = (drafts[first_bench][1], drafts[second_bench][1])
            first_report = issue_comparison(center, *reversed(old_sources))
            first_pickup = read_comparison(center, first_report.report_id)

            bench = correction['bench_id']
            with closing(sqlite3.connect(site_paths[bench])) as site:
                initialize_site(site)
                corrected_revision = record_readings(
                    site, round_id, bench, correction['readings'], corrects=drafts[bench][0],
                )
                corrected_wire = issue_wire(site, corrected_revision)
                accepted[bench] = accept_summary(center, corrected_wire)
            new_sources = (accepted[first_bench], accepted[second_bench])
            new_wires = tuple(corrected_wire if slot == bench else drafts[slot][1]
                              for slot in (first_bench, second_bench))
            next_report = issue_comparison(center, *reversed(new_sources))

        with closing(sqlite3.connect(center_path)) as center:
            initialize_acceptance_store(center)
            initialize_comparison_store(center)
            reopened_old = read_comparison(center, first_report.report_id)
            reopened_new = read_comparison(center, next_report.report_id)

        first_expected = [['B', '1/2', 2, '1/2'], ['A', '4', 1, '0']]
        corrected_expected = [['B', '3/2', 2, '9/2'], ['A', '4', 1, '0']]
        print_scenario(
            'closed_sites', {'work_order': work, 'readings': data['first_pass'],
                             'selection': list(reversed(old_sources))},
            first_expected, display_rows(first_report),
            {'rows': first_expected, 'fixed_sources_and_receipt': True},
            {'rows': display_rows(first_pickup.report),
             'fixed_sources_and_receipt': pickup_matches(first_pickup, first_report, old_wires, old_sources)},
            ['protocol/nominals.py', 'fit/local_reports.py', 'exchange/issue.py',
             'exchange/accept.py', 'review/publish.py', 'review/readback.py'],
            'B 的名义值为 -1 和 2，残差 1 和 0 给出均值 1/2 和平方和 1/2。A 单行残差为 7−3=4。工单顺序为 B、A。',
        )
        print_scenario(
            'historical', {'correction': correction, 'prior_revision': drafts[bench][0],
                           'corrected_revision': corrected_revision,
                           'report_numbers': [first_report.report_id, next_report.report_id]},
            [first_expected, corrected_expected], [display_rows(first_report), display_rows(next_report)],
            {'rows': [first_expected, corrected_expected], 'fixed_sources_and_receipts': True, 'distinct_reports': True},
            {'rows': [display_rows(reopened_old.report), display_rows(reopened_new.report)],
             'fixed_sources_and_receipts': pickup_matches(reopened_old, first_report, old_wires, old_sources)
             and pickup_matches(reopened_new, next_report, new_wires, new_sources),
             'distinct_reports': first_report.report_id != next_report.report_id},
            ['intake/corrections.py', 'intake/freeze.py', 'fit/local_reports.py',
             'review/register.py', 'exchange/catalog.py', 'review/readback.py'],
            '勘误后的 B 残差为 3 和 0，均值为 3/2，两个中心化偏差各贡献 9/4。旧号仍应使用原来两个首纳件。',
        )


if __name__ == '__main__':
    main()
