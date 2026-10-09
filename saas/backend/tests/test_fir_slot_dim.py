"""Slot dimn: Parameter contains 'slot' and spec is length×dia (NxM) → +0.5 each.

Mirrors saas/backend/static/fir_preview_runtime.js parseSlotDimSpec / isWithinSlotSpec.
"""

from __future__ import annotations

import re

SLOT_PLUS = 0.5
_SLOT_PAIR = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*[xX×]\s*([0-9]+(?:\.[0-9]+)?)")


def fir_is_slot_param(param: str | None) -> bool:
    return bool(re.search(r"slot", param or "", re.I))


def parse_slot_dim_spec(spec: str | None, param: str | None):
    if not fir_is_slot_param(param):
        return None
    m = _SLOT_PAIR.search(spec or "")
    if not m:
        return None
    length = float(m.group(1))
    dia = float(m.group(2))
    return {
        "length": length,
        "dia": dia,
        "lengthMin": length,
        "lengthMax": length + SLOT_PLUS,
        "diaMin": dia,
        "diaMax": dia + SLOT_PLUS,
    }


def parse_slot_observed(value: str | None):
    m = _SLOT_PAIR.search(value or "")
    if not m:
        return None
    return {"length": float(m.group(1)), "dia": float(m.group(2))}


def is_within_slot_spec(value: str | None, spec: str, param: str) -> bool:
    rng = parse_slot_dim_spec(spec, param)
    pair = parse_slot_observed(value)
    if not rng or not pair:
        return False
    return (
        rng["lengthMin"] <= pair["length"] <= rng["lengthMax"]
        and rng["diaMin"] <= pair["dia"] <= rng["diaMax"]
    )


def remarks_ok(values: list[str], spec: str, param: str) -> str:
    if values and all(is_within_slot_spec(v, spec, param) for v in values):
        return "OK"
    return "Not OK"


def test_slot_keyword_and_nxm_gets_plus_half():
    rng = parse_slot_dim_spec("23 X 13", "1 Slot Dimn")
    assert rng is not None
    assert rng["length"] == 23
    assert rng["dia"] == 13
    assert rng["lengthMin"] == 23
    assert rng["lengthMax"] == 23.5
    assert rng["diaMin"] == 13
    assert rng["diaMax"] == 13.5


def test_parenthesized_and_compact_spec_forms():
    for spec in ("(23X13)", "23X13", "23 x 13", "23×13"):
        rng = parse_slot_dim_spec(spec, "SLOT")
        assert rng is not None, spec
        assert rng["length"] == 23 and rng["dia"] == 13


def test_without_slot_keyword_is_not_slot_dim():
    assert parse_slot_dim_spec("23X13", "Overall length") is None
    assert parse_slot_dim_spec("23 X 13", "Hole dia") is None


def test_slot_param_without_nxm_is_not_slot_dim():
    assert parse_slot_dim_spec("23 ± 0.1", "1 Slot Dimn") is None
    assert parse_slot_dim_spec("R3", "slot") is None


def test_observed_format_and_in_tolerance_ok():
    param, spec = "1 Slot Dimn", "23X13"
    assert is_within_slot_spec("23.2X13.1", spec, param)
    assert is_within_slot_spec("23.0X13.0", spec, param)
    assert is_within_slot_spec("23.5X13.5", spec, param)
    assert is_within_slot_spec("23.2 X 13.1", spec, param)
    assert remarks_ok(["23.2X13.1", "23.1X13.4", "23.5X13.0"], spec, param) == "OK"


def test_out_of_tolerance_not_ok():
    param, spec = "1 Slot Dimn", "23X13"
    assert not is_within_slot_spec("23.6X13.1", spec, param)  # length over +0.5
    assert not is_within_slot_spec("22.9X13.1", spec, param)  # length below nominal
    assert not is_within_slot_spec("23.2X13.6", spec, param)  # dia over +0.5
    assert remarks_ok(["23.2X13.1", "23.6X13.1"], spec, param) == "Not OK"
