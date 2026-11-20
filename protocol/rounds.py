import json
import sqlite3
from dataclasses import dataclass

from protocol.nominals import LineNominal, calculate_nominals
from protocol.quantities import format_rational, parse_rational
from protocol.recipes import BenchRecipe, build_bench_recipe
from protocol.references import ReferenceSet, build_reference_set, named_pairs, require_name


@dataclass(frozen=True)
class RoundPlan:
    round_id: str
    references: ReferenceSet
    recipes: tuple[BenchRecipe, BenchRecipe]
    nominals: tuple[tuple[LineNominal, ...], tuple[LineNominal, ...]]

    @property
    def bench_order(self) -> tuple[str, str]:
        return self.recipes[0].bench_id, self.recipes[1].bench_id

    def bench(self, bench_id: str) -> tuple[BenchRecipe, tuple[LineNominal, ...]]:
        for recipe, nominals in zip(self.recipes, self.nominals, strict=True):
            if recipe.bench_id == bench_id:
                return recipe, nominals
        raise ValueError(f'bench {bench_id!r} is outside round {self.round_id!r}')


def initialize_round_store(db: sqlite3.Connection) -> None:
    db.execute('PRAGMA foreign_keys = ON')
    db.execute('''
        CREATE TABLE IF NOT EXISTS rounds (
            round_id TEXT PRIMARY KEY NOT NULL,
            snapshot TEXT NOT NULL
        )
    ''')


def _encode_plan(plan: RoundPlan) -> str:
    benches = []
    for recipe, nominals in zip(plan.recipes, plan.nominals, strict=True):
        lines = []
        for line, nominal in zip(recipe.lines, nominals, strict=True):
            terms = [(term.reference, format_rational(term.sensitivity)) for term in line.terms]
            lines.append((line.name, terms, format_rational(nominal.value)))
        benches.append((recipe.bench_id, lines))
    return json.dumps({
        'references': [(item.name, format_rational(item.nominal)) for item in plan.references.entries],
        'benches': benches,
    })


def register_round(db: sqlite3.Connection, round_id: str, references, benches) -> RoundPlan:
    require_name(round_id, 'round')
    fixed_references = build_reference_set(references)
    pairs = tuple(named_pairs(benches, 'bench'))
    if len(pairs) != 2:
        raise ValueError('a round requires exactly two distinct benches')
    first = build_bench_recipe(*pairs[0], fixed_references)
    second = build_bench_recipe(*pairs[1], fixed_references)
    plan = RoundPlan(
        round_id,
        fixed_references,
        (first, second),
        (calculate_nominals(fixed_references, first), calculate_nominals(fixed_references, second)),
    )
    snapshot = _encode_plan(plan)
    db.execute('BEGIN IMMEDIATE')
    with db:
        cursor = db.execute('''
            INSERT INTO rounds (round_id, snapshot) VALUES (?, ?)
            ON CONFLICT (round_id) DO NOTHING
        ''', (round_id, snapshot))
        if cursor.rowcount != 1:
            raise ValueError(f'round already registered: {round_id}')
    return plan


def get_round(db: sqlite3.Connection, round_id: str) -> RoundPlan:
    if not isinstance(round_id, str):
        raise KeyError(round_id)
    row = db.execute('SELECT snapshot FROM rounds WHERE round_id = ?', (round_id,)).fetchone()
    if row is None:
        raise KeyError(round_id)
    snapshot = json.loads(row[0])
    references = build_reference_set(snapshot['references'])
    recipes = []
    nominals = []
    for bench_id, lines in snapshot['benches']:
        recipes.append(build_bench_recipe(bench_id, [(name, terms) for name, terms, _ in lines], references))
        nominals.append(tuple(LineNominal(name, parse_rational(value)) for name, _, value in lines))
    first, second = recipes
    first_nominals, second_nominals = nominals
    return RoundPlan(round_id, references, (first, second), (first_nominals, second_nominals))
