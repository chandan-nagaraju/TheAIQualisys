from app.part_field_validation import sanitize_part_master_alnum_upper, sanitize_part_master_description


def test_part_no_still_strips_spaces() -> None:
    assert sanitize_part_master_alnum_upper("BZ G0 J404") == "BZG0J404"


def test_description_keeps_spaces_between_words() -> None:
    assert sanitize_part_master_description("COOLENT IN PIPE") == "COOLENT IN PIPE"
    assert sanitize_part_master_description("TURBO CHARGER OIL- IN PIPE") == "TURBO CHARGER OIL- IN PIPE"
    assert sanitize_part_master_description("  TURBO   CHARGER  ") == "TURBO CHARGER"
