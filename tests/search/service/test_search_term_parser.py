"""The term parser is pure: capabilities in, no DB anywhere."""

from app.search.search_term_parser import parse_search_term


def test_slash_period_normalizes_to_db_form():
    parsed = parse_search_term("03/2026")
    assert parsed.classification == "period"
    assert parsed.period == "2026-03"
    assert parsed.activates_text is True
    assert parsed.integer is None


def test_single_digit_month_is_zero_padded():
    assert parse_search_term("3/2026").period == "2026-03"


def test_db_form_period_passes_through():
    assert parse_search_term("2026-03").period == "2026-03"


def test_impossible_months_are_not_periods():
    assert parse_search_term("13/2026").period is None
    assert parse_search_term("0/2026").period is None
    assert parse_search_term("2026-13").period is None
    assert parse_search_term("2026-00").period is None


def test_period_shaped_term_still_activates_text_branches():
    """A filename can legitimately be `2026-03` — period terms are not exclusive."""
    parsed = parse_search_term("2026-03")
    assert parsed.period is not None
    assert parsed.activates_text is True


def test_bare_integer_is_an_identifier_not_text():
    parsed = parse_search_term("307")
    assert parsed.classification == "integer"
    assert parsed.integer == 307
    assert parsed.tax_year is None
    assert parsed.activates_text is False


def test_year_heuristic_bounds():
    assert parse_search_term("1989").tax_year is None
    assert parse_search_term("1990").tax_year == 1990
    assert parse_search_term("2100").tax_year == 2100
    assert parse_search_term("2101").tax_year is None


def test_plausible_year_is_also_a_plain_integer():
    parsed = parse_search_term("2026")
    assert parsed.integer == 2026
    assert parsed.tax_year == 2026


def test_oversized_digit_run_carries_no_integer():
    """Larger than int32 would blow up an `id == term` comparison in Postgres."""
    parsed = parse_search_term("99999999999999999999")
    assert parsed.integer is None
    assert parsed.tax_year is None
    assert parsed.activates_text is False


def test_text_term_activates_only_text():
    parsed = parse_search_term("audit_2026.pdf")
    assert parsed.classification == "text"
    assert parsed.period is None
    assert parsed.integer is None
    assert parsed.activates_text is True


def test_mixed_digits_and_letters_are_text():
    parsed = parse_search_term("A-307")
    assert parsed.integer is None
    assert parsed.activates_text is True
