"""V2 evidence encoding, acceptance validation and catalog rules."""
import json
import sqlite3

from exchange.accept import accept_isolation_evidence, accept_summary
from exchange.isolation_catalog import (
    format_acceptance_id,
    get_accepted_evidence,
    parse_acceptance_id,
)
from exchange.isolation_codec import decode_isolation_evidence, encode_isolation_evidence
from exchange.issue import issue_isolation_evidence, issue_summary
from fit.isolation_relations import AffineRelation
from tests.isolation_support import IsolationCase


class AcceptanceIdTests(IsolationCase):
    def test_format_parse(self):
        self.assertEqual(format_acceptance_id(1), 'v2:1')
        self.assertEqual(parse_acceptance_id('v2:12'), 12)
        for bad in ('v2:0', 'v2:01', 'v1:1', 'v2:', 'v2', 'x:1', 1, None, 'v2:-1', 'v2:1.0'):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    parse_acceptance_id(bad)

    def test_unknown_but_well_formed_id_is_key_error(self):
        center = self.open_center()
        with self.assertRaises(KeyError):
            get_accepted_evidence(center, 'v2:999')
        with self.assertRaises(ValueError):
            get_accepted_evidence(center, 'v2:01')


class WireCodecTests(IsolationCase):
    def setUp(self):
        super().setUp()
        self.site = self.open_site()
        self.register(self.site)
        _, freeze_id = self.frozen(self.site, 'round-1', 'B', [('a', 0), ('b', 2)])
        self.wire = issue_isolation_evidence(self.site, freeze_id)

    def test_wire_shape_and_round_trip(self):
        payload = json.loads(self.wire)
        self.assertEqual(set(payload), {
            'version', 'round_id', 'bench_id', 'revision_id', 'bench_order',
            'reference_order', 'relation',
        })
        self.assertEqual(payload['version'], 2)
        self.assertEqual(payload['bench_order'], ['B', 'A'])
        self.assertEqual(payload['reference_order'], ['X', 'Y'])
        evidence = decode_isolation_evidence(self.wire)
        self.assertEqual(encode_isolation_evidence(evidence), self.wire)
        self.assertEqual(evidence.bench_id, 'B')
        self.assertIsInstance(evidence.revision_id, int)

    def test_full_and_empty_relation_kinds(self):
        _, single_freeze = self.frozen(self.site, 'round-1', 'B', [('b', 2)])
        full_wire = issue_isolation_evidence(self.site, single_freeze)
        self.assertEqual(json.loads(full_wire)['relation'], {'kind': 'full'})
        decoded_full = decode_isolation_evidence(full_wire)
        self.assertEqual(decoded_full.relation, AffineRelation('full', 2))

        contradictory_site = self.open_site('contradiction')
        self.register(contradictory_site)
        # p and q share the same X sensitivity, so differing residuals cannot
        # be explained by one station zero: the relation must be empty.
        _, bad_freeze = self.frozen(
            contradictory_site, 'round-1', 'A', [('p', 2), ('p_repeat', 5)])
        empty_wire = issue_isolation_evidence(contradictory_site, bad_freeze)
        self.assertEqual(json.loads(empty_wire)['relation'], {'kind': 'empty'})
        self.assertEqual(decode_isolation_evidence(empty_wire).relation.kind, 'empty')

    def test_rejects_bad_wires(self):
        valid = json.loads(self.wire)
        malformed = [None, [], '', '[]', '{', '{"version":2,}']
        # Missing and extra fields.
        missing = dict(valid)
        del missing['relation']
        malformed.append(json.dumps(missing))
        extra = dict(valid)
        extra['unexpected'] = 1
        malformed.append(json.dumps(extra))
        # Version and type problems.
        for field, value in (
            ('version', 1), ('version', 3), ('version', True), ('version', '2'),
            ('round_id', ''), ('bench_id', 'outside'),
            ('bench_order', ['B', 'B']), ('bench_order', ['B']), ('bench_order', 'BA'),
            ('reference_order', []), ('reference_order', ['X', 'X']),
            ('revision_id', 0), ('revision_id', True), ('revision_id', 2**63),
        ):
            malformed.append(json.dumps({**valid, field: value}))
        # Duplicate JSON keys.
        malformed.append('{"version":2,' + self.wire[1:])
        # Relation representation problems.
        relation_bad = [
            {'kind': 'nope'},
            {'kind': 'full', 'equations': []},
            {'kind': 'system'},
            {'kind': 'system', 'equations': []},
            {'kind': 'system', 'equations': [{'coefficients': ['1'], 'rhs': '0'}]},
            {'kind': 'system', 'equations': [{'coefficients': ['1', None], 'rhs': '0'}]},
            {'kind': 'system', 'equations': [{'coefficients': ['1', '0.5'], 'rhs': '1/0'}]},
            {'kind': 'system', 'equations': [{'coefficients': ['0', '0'], 'rhs': '1'}]},
            {'kind': 'system', 'equations': [
                {'coefficients': ['1', '0'], 'rhs': '0'}, {'extra': 1}]},
        ]
        for relation in relation_bad:
            broken = dict(valid)
            broken['relation'] = relation
            malformed.append(json.dumps(broken))
        # NaN / Infinity are invalid JSON constants here.
        malformed.append(self.wire.replace('"version":2', '"version":2', 1).replace('{', '{"x":NaN,', 1))
        for wire in malformed:
            with self.subTest(wire=wire):
                with self.assertRaises(ValueError):
                    decode_isolation_evidence(wire)

    def test_equivalent_rational_relation_accepted_once(self):
        center = self.open_center()
        first_id = accept_isolation_evidence(center, self.wire)
        payload = json.loads(self.wire)
        if payload['relation']['kind'] == 'system':
            for equation in payload['relation']['equations']:
                equation['coefficients'] = [
                    value + '/1' if value.lstrip('-').isdigit() else value
                    for value in equation['coefficients']
                ]
        equivalent = json.dumps(payload, indent=2)
        self.assertNotEqual(equivalent, self.wire)
        self.assertEqual(accept_isolation_evidence(center, equivalent), first_id)
        self.assertEqual(get_accepted_evidence(center, first_id).wire, self.wire)

    def test_conflicting_relation_for_identity_rejected(self):
        center = self.open_center()
        first_id = accept_isolation_evidence(center, self.wire)
        payload = json.loads(self.wire)
        payload['relation'] = {'kind': 'empty'}
        with self.assertRaises(ValueError):
            accept_isolation_evidence(center, json.dumps(payload))
        self.assertEqual(get_accepted_evidence(center, first_id).wire, self.wire)

    def test_v1_body_rejected_by_v2_acceptance_and_reverse(self):
        center = self.open_center()
        # Build a V1 body through the real V1 entry point.
        from fit.local_reports import issue_local
        from intake.freeze import freeze_revision
        revision, _ = self.frozen(self.site, 'round-1', 'B', [('a', 0), ('b', 2)])
        v1_wire = issue_summary(self.site, issue_local(self.site, freeze_revision(self.site, revision)).report_id)
        with self.assertRaises(ValueError):
            accept_isolation_evidence(center, v1_wire)
        v1_id = accept_summary(center, v1_wire)
        self.assertIsInstance(v1_id, int)
        with self.assertRaises((ValueError, KeyError)):
            get_accepted_evidence(center, format_acceptance_id(v1_id))

    def test_unknown_freeze_is_key_error(self):
        with self.assertRaises(KeyError):
            issue_isolation_evidence(self.site, 999)

    def test_acceptance_write_rollback_and_retry(self):
        center = self.open_center()
        self.center = center
        center.execute('''
            CREATE TEMP TRIGGER reject_evidence BEFORE INSERT ON accepted_evidence
            BEGIN SELECT RAISE(ABORT, 'evidence fixture'); END
        ''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'evidence fixture'):
            accept_isolation_evidence(center, self.wire)
        self.assertFalse(center.in_transaction)
        self.assertEqual(center.execute('SELECT count(*) FROM accepted_evidence').fetchone()[0], 0)
        center.execute('DROP TRIGGER reject_evidence')
        acceptance_id = accept_isolation_evidence(center, self.wire)
        self.assertEqual(get_accepted_evidence(center, acceptance_id).wire, self.wire)

    def test_json_constants_rejected(self):
        for constant in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(constant=constant):
                with self.assertRaises(ValueError):
                    decode_isolation_evidence(f'{{"bad":{constant}}}')
