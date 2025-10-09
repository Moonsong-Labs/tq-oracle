from __future__ import annotations

from tq_oracle.units import scale_to_18


def test_scale_to_18_same_decimals():
    assert scale_to_18(123, 18) == 123


def test_scale_to_18_scale_up():
    assert scale_to_18(1, 6) == 10**12
    assert scale_to_18(10**8, 8) == 10**18


def test_scale_to_18_scale_down():
    assert scale_to_18(10**20, 20) == 10**18
    assert scale_to_18(100, 20) == 1
