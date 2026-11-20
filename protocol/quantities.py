import re
from fractions import Fraction

READING_UNIT = 'µm'

_INTEGER = re.compile(r'[+-]?[0-9]+')
_DECIMAL = re.compile(r'[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+)')


def parse_rational(value) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if type(value) is int:
        return Fraction(value)
    if isinstance(value, str):
        text = value.strip()
        numerator, slash, denominator = text.partition('/')
        if slash and _INTEGER.fullmatch(numerator) and _INTEGER.fullmatch(denominator):
            try:
                return Fraction(int(numerator), int(denominator))
            except ZeroDivisionError as exc:
                raise ValueError('zero denominator') from exc
        if _INTEGER.fullmatch(text) or _DECIMAL.fullmatch(text):
            return Fraction(text)
    raise ValueError('expected an integer, Fraction, or exact rational text')


def format_rational(value) -> str:
    return str(parse_rational(value))


def lookup_id(value) -> int:
    if type(value) is not int or not 1 <= value <= 2**63 - 1:
        raise KeyError(value)
    return value
