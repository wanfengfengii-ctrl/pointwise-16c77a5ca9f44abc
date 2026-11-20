from dataclasses import dataclass
from fractions import Fraction

from protocol.quantities import parse_rational


def require_name(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a nonempty name')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise ValueError(f'{label} must be valid Unicode') from exc
    return value


def named_pairs(entries, label: str):
    if not isinstance(entries, (list, tuple)):
        raise ValueError(f'{label} must be an ordered list or tuple of pairs')
    seen = set()
    for entry in entries:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError(f'{label} requires name and value pairs')
        name, value = entry
        require_name(name, label)
        if name in seen:
            raise ValueError(f'duplicate {label}: {name}')
        seen.add(name)
        yield name, value


@dataclass(frozen=True)
class Reference:
    name: str
    nominal: Fraction


@dataclass(frozen=True)
class ReferenceSet:
    entries: tuple[Reference, ...]

    def nominal_by_name(self) -> dict[str, Fraction]:
        return {reference.name: reference.nominal for reference in self.entries}


def build_reference_set(entries) -> ReferenceSet:
    references = tuple(
        Reference(name, parse_rational(value))
        for name, value in named_pairs(entries, 'reference')
    )
    if not references:
        raise ValueError('a round requires references')
    return ReferenceSet(references)
