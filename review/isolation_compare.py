"""Joint minimum-isolation determination from two station relations."""
from dataclasses import dataclass

from fit.isolation_relations import (
    intersect_relations,
    minimum_isolation,
)

STATUS_OK = 'ok'
STATUS_IMPOSSIBLE = 'impossible'


@dataclass(frozen=True)
class IsolationOutcome:
    status: str
    minimum_count: int | None
    required_references: tuple[str, ...]


def determine_isolation(selection) -> IsolationOutcome:
    """Combine the two relations in their shared reference coordinates."""
    first, second = selection.evidence
    joint = intersect_relations(first.evidence.relation, second.evidence.relation)
    minimum_count, required_positions, feasible = minimum_isolation(joint)
    if not feasible:
        return IsolationOutcome(STATUS_IMPOSSIBLE, None, ())
    reference_order = selection.reference_order
    required = tuple(
        reference_order[position]
        for position in range(len(reference_order))
        if position in required_positions
    )
    return IsolationOutcome(STATUS_OK, minimum_count, required)
