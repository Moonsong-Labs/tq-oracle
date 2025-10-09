from __future__ import annotations


def scale_to_18(value: int, decimals: int) -> int:
    """Scale an integer amount to 18 decimals.

    Args:
        value: Integer amount expressed with ``decimals`` decimal places.
        decimals: Current decimal precision of ``value``.

    Returns:
        The amount scaled to 18-decimal precision.

    Notes:
        - If ``decimals`` < 18, multiplies by 10**(18 - decimals).
        - If ``decimals`` > 18, uses integer division (truncates toward zero).
        - Intended for fixed-point on-chain style values.
    """
    if decimals == 18:
        return value
    if decimals < 18:
        return value * (10 ** (18 - decimals))
    return value // (10 ** (decimals - 18))
