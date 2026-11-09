import pytest

from cronlens import CronParseError, parse
from cronlens.fields import DAY_OF_WEEK, MINUTE, MONTH
from cronlens.parser import MACROS, parse_field


def values(raw, spec=MINUTE):
    return parse_field(raw, spec).sorted_values()


class TestParseField:
    def test_wildcard_covers_whole_range(self):
        assert values("*") == list(range(60))

    def test_single_value(self):
        assert values("7") == [7]

    def test_range(self):
        assert values("10-14") == [10, 11, 12, 13, 14]

    def test_list(self):
        assert values("1,5,9") == [1, 5, 9]

    def test_step_over_wildcard(self):
        assert values("*/15") == [0, 15, 30, 45]

    def test_step_inside_range(self):
        assert values("10-40/10") == [10, 20, 30, 40]

    def test_step_from_start_value(self):
        assert values("50/5") == [50, 55]

    def test_mixed_list(self):
        assert values("0-2,30,*/20") == [0, 1, 2, 20, 30, 40]

    def test_duplicates_collapse(self):
        assert values("5,5,1-5") == [1, 2, 3, 4, 5]

    def test_day_of_week_seven_is_sunday(self):
        assert values("7", DAY_OF_WEEK) == [0]
        assert values("5-7", DAY_OF_WEEK) == [0, 5, 6]

    def test_day_of_week_wildcard_is_full(self):
        field = parse_field("*", DAY_OF_WEEK)
        assert field.sorted_values() == list(range(7))
        assert field.is_full

    @pytest.mark.parametrize(
        "raw",
        ["60", "-1", "a", "5-", "-5", "10-5", "*/0", "*/x", "1,,2", "", "1-2-3"],
    )
    def test_invalid(self, raw):
        with pytest.raises(CronParseError) as info:
            parse_field(raw, MINUTE)
        assert info.value.field == "minute"


class TestNames:
    def test_month_names(self):
        assert values("jan", MONTH) == [1]
        assert values("JAN,Jul,dec", MONTH) == [1, 7, 12]

    def test_month_name_range_with_step(self):
        assert values("jan-dec/3", MONTH) == [1, 4, 7, 10]

    def test_weekday_names(self):
        assert values("mon-fri", DAY_OF_WEEK) == [1, 2, 3, 4, 5]
        assert values("sat,sun", DAY_OF_WEEK) == [0, 6]

    def test_names_mix_with_numbers(self):
        assert values("1-wed", DAY_OF_WEEK) == [1, 2, 3]

    def test_names_only_apply_to_their_field(self):
        with pytest.raises(CronParseError):
            parse_field("mon", MONTH)
        with pytest.raises(CronParseError):
            parse_field("jan", MINUTE)

    def test_named_expression(self):
        expr = parse("30 4 * jun-aug mon,wed")
        assert expr.month.sorted_values() == [6, 7, 8]
        assert expr.day_of_week.sorted_values() == [1, 3]


class TestMacros:
    @pytest.mark.parametrize("macro", sorted(MACROS))
    def test_macros_expand(self, macro):
        expr = parse(macro)
        assert expr.source == macro
        assert expr.normalized == MACROS[macro]

    def test_macros_are_case_insensitive(self):
        assert parse("@DAILY").normalized == "0 0 * * *"

    def test_reboot_has_no_schedule(self):
        with pytest.raises(CronParseError, match="startup"):
            parse("@reboot")

    def test_unknown_macro(self):
        with pytest.raises(CronParseError, match="unknown macro"):
            parse("@fortnightly")


class TestParse:
    def test_fields_are_assigned_in_order(self):
        expr = parse("1 2 3 4 5")
        assert expr.minute.values == {1}
        assert expr.hour.values == {2}
        assert expr.day_of_month.values == {3}
        assert expr.month.values == {4}
        assert expr.day_of_week.values == {5}

    def test_extra_whitespace_is_ignored(self):
        expr = parse("  */5   *  *\t* *  ")
        assert expr.normalized == "*/5 * * * *"
        assert expr.minute.sorted_values() == list(range(0, 60, 5))

    def test_str_returns_source(self):
        assert str(parse("0 0 * * *")) == "0 0 * * *"

    def test_wildcard_flags(self):
        expr = parse("0 0 */2 * 1")
        assert expr.day_of_month.is_wildcard
        assert not expr.day_of_month.is_full
        assert not expr.day_of_week.is_wildcard

    @pytest.mark.parametrize("text", ["", "   ", "* * * *", "* * * * * *"])
    def test_wrong_field_count(self, text):
        with pytest.raises(CronParseError):
            parse(text)

    def test_error_reports_field_and_expression(self):
        with pytest.raises(CronParseError) as info:
            parse("0 25 * * *")
        assert info.value.field == "hour"
        assert info.value.expression == "0 25 * * *"
        assert "out of range" in str(info.value)

    @pytest.mark.parametrize(
        "text", ["0 0 0 * *", "0 0 32 * *", "0 0 * 0 *", "0 0 * 13 *", "0 0 * * 8"]
    )
    def test_out_of_range_dates(self, text):
        with pytest.raises(CronParseError):
            parse(text)
