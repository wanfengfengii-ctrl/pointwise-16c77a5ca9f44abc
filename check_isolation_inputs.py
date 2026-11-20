import json
import sqlite3
from contextlib import closing

from demo import display_rows, initialize_site, issue_wire, pickup_matches
from exchange.accept import accept_summary
from exchange.catalog import initialize_acceptance_store
from intake.measurements import record_readings
from protocol.rounds import register_round
from review.publish import issue_comparison
from review.readback import read_comparison
from review.register import initialize_comparison_store


SAMPLE = {
    "round_id": "relay-12",
    "references": [["X", 2], ["Y", 3]],
    "benches": [
        ["B", [["a", [["X", 1]]], ["b", [["Y", -1]]]]],
        ["A", [["p", [["X", 1]]], ["q", [["Y", 1]]], ["r", [["Y", -1]]],
               ["p_repeat", [["X", 1]]]]],
    ],
    "revisions": {
        "B": {
            "initial": [["b", -3], ["a", 3]],
            "opposite": [["a", 2], ["b", -2]],
            "shifted": [["a", 8], ["b", 2]],
            "zero": [["a", 2], ["b", -3]],
        },
        "A": {
            "equal": [["p", 2], ["q", 3]],
            "sum1": [["p", 3], ["r", -3]],
            "sum2": [["p", 4], ["r", -3]],
            "single": [["q", 3]],
            "contradictory": [["p", 2], ["p_repeat", 3]],
        },
    },
    "cases": [
        {"name": "joint", "select": ["initial", "equal"], "expected": ["ok", 2, ["X", "Y"]]},
        {"name": "shift", "select": ["shifted", "equal"], "expected": ["ok", 2, ["X", "Y"]]},
        {"name": "tie", "select": ["initial", "sum1"], "expected": ["ok", 1, []]},
        {"name": "same_summary", "select": ["opposite", "sum1"], "expected": ["impossible", None, []]},
        {"name": "different_sums", "select": ["initial", "sum2"], "expected": ["impossible", None, []]},
        {"name": "zero", "select": ["zero", "equal"], "expected": ["ok", 0, []]},
        {"name": "single", "select": ["initial", "single"], "expected": ["ok", 1, []]},
        {"name": "contradictory", "select": ["initial", "contradictory"], "expected": ["impossible", None, []]},
    ],
}


def check(sample):
    order = tuple(bench for bench, _ in sample["benches"])
    accepted = {}
    comparisons = {}
    with closing(sqlite3.connect(":memory:")) as center:
        initialize_acceptance_store(center)
        initialize_comparison_store(center)
        for bench in order:
            with closing(sqlite3.connect(":memory:")) as site:
                initialize_site(site)
                register_round(site, sample["round_id"], sample["references"], sample["benches"])
                parent = None
                for name, readings in sample["revisions"][bench].items():
                    revision = record_readings(site, sample["round_id"], bench, readings, corrects=parent)
                    if parent is None:
                        parent = revision
                    wire = issue_wire(site, revision)
                    accepted[bench, name] = (accept_summary(center, wire), wire)

        for case in sample["cases"]:
            name = case["name"]
            sources, wires = zip(*(accepted[key] for key in zip(order, case["select"], strict=True)))
            report = issue_comparison(center, *reversed(sources))
            pickup = read_comparison(center, report.report_id)
            if not pickup_matches(pickup, report, wires, sources):
                raise AssertionError(f"{name}: V1 pickup lost its source")
            comparisons[name] = display_rows(report)

    expected = [["B", "1/2", 2, "1/2"], ["A", "1/2", 2, "1/2"]]
    tie, opposite = comparisons["tie"], comparisons["same_summary"]
    if tie != expected or opposite != expected:
        raise AssertionError(f"unexpected V1 comparison: {tie!r} / {opposite!r}")
    print(json.dumps({"v1_tie": tie, "v1_same_summary": opposite,
                      "checked_selections": len(comparisons)}, sort_keys=True))


if __name__ == "__main__":
    check(SAMPLE)
