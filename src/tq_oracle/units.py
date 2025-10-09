from __future__ import annotations


def scale_to_18(value: int, decimals: int) -> int:
    if decimals == 18:
        return value
    if decimals < 18:
        return value * (10 ** (18 - decimals))
    return value // (10 ** (decimals - 18))
