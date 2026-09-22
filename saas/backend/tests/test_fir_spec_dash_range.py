"""Document dash-range vs unilateral-minus (mirrors fir_preview_runtime parseSpec)."""


def _dash_pair_is_explicit_limits(a: float, b: float) -> bool:
    lo, hi = min(a, b), max(a, b)
    return hi > 0 and lo / hi >= 0.5


def test_fourteen_minus_point_three_is_not_a_zero_to_fourteen_band() -> None:
    assert not _dash_pair_is_explicit_limits(14, 0.3)
    assert not _dash_pair_is_explicit_limits(8.5, 0.2)
    assert _dash_pair_is_explicit_limits(95.5, 96)
    assert _dash_pair_is_explicit_limits(8, 12)
    assert _dash_pair_is_explicit_limits(0.8, 1.2)
