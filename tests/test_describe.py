import pytest

from cronlens import parse
from cronlens.describe import compact_values, describe, join_words, ordinal


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("* * * * *", "Every minute"),
        ("*/5 * * * *", "Every 5 minutes"),
        ("*/7 * * * *", "At every 7th minute"),
        ("0,30 * * * *", "Every 30 minutes"),
        ("5-55/10 * * * *", "Every 10 minutes from minute 5 through 55"),
        ("0-10 * * * *", "Every minute from minute 0 through 10"),
        ("0 * * * *", "At minute 0 past every hour"),
        ("15 */2 * * *", "At minute 15 past every 2nd hour"),
        ("0 8-18/2 * * *", "At minute 0 past every 2nd hour from 8 through 18"),
        ("* 9 * * *", "Every minute, between 09:00 and 09:59"),
        ("*/15 9-17 * * *", "Every 15 minutes, between 09:00 and 17:59"),
        ("*/10 8-18/2 * * *", "Every 10 minutes, during every 2nd hour from 8 through 18"),
    ],
)
def test_minutes_and_hours(expression, expected):
    assert describe(parse(expression)) == expected


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("30 2 * * *", "At 02:30"),
        ("0 9,17 * * *", "At 09:00 and 17:00"),
        ("0 */6 * * *", "At 00:00, 06:00, 12:00 and 18:00"),
        ("0,30 9 * * *", "At 09:00 and 09:30"),
    ],
)
def test_specific_times_are_listed(expression, expected):
    assert describe(parse(expression)) == expected


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("30 2 * * 1-5", "At 02:30, on weekdays"),
        ("0 10 * * sat,sun", "At 10:00, on weekends"),
        ("0 0 * * 0", "At 00:00, on Sunday"),
        ("0 4 * * mon,wed,fri", "At 04:00, on Monday, Wednesday and Friday"),
        ("0 9-17 * * 1-5", "At minute 0 past every hour from 9 through 17, on weekdays"),
        ("0 0 1 * *", "At 00:00, on the 1st of the month"),
        ("0 0 1,15 * *", "At 00:00, on the 1st and 15th of the month"),
        ("0 0 */2 * *", "At 00:00, on every 2nd day of the month"),
        (
            "0 0 1-15/2 * *",
            "At 00:00, on every 2nd day of the month from the 1st through the 15th",
        ),
    ],
)
def test_days(expression, expected):
    assert describe(parse(expression)) == expected


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("0 12 * 6-8 *", "At 12:00, in June through August"),
        ("0 0 * jan,jul *", "At 00:00, in January and July"),
        ("0 0 1 */3 *", "At 00:00, on the 1st of the month, every 3rd month"),
        ("0 0 1 1 *", "At 00:00, on January 1st"),
        ("0 0 29 2 *", "At 00:00, on February 29th"),
    ],
)
def test_months(expression, expected):
    assert describe(parse(expression)) == expected


@pytest.mark.parametrize(
    ("macro", "expected"),
    [
        ("@yearly", "At 00:00, on January 1st"),
        ("@monthly", "At 00:00, on the 1st of the month"),
        ("@weekly", "At 00:00, on Sunday"),
        ("@daily", "At 00:00"),
        ("@hourly", "At minute 0 past every hour"),
    ],
)
def test_macros(macro, expected):
    assert describe(parse(macro)) == expected


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (1, "1st"),
        (2, "2nd"),
        (3, "3rd"),
        (4, "4th"),
        (11, "11th"),
        (12, "12th"),
        (13, "13th"),
        (21, "21st"),
        (22, "22nd"),
        (31, "31st"),
        (111, "111th"),
    ],
)
def test_ordinal(number, expected):
    assert ordinal(number) == expected


def test_join_words():
    assert join_words([]) == ""
    assert join_words(["a"]) == "a"
    assert join_words(["a", "b"]) == "a and b"
    assert join_words(["a", "b", "c"]) == "a, b and c"


def test_compact_values():
    assert compact_values(list(range(0, 60, 5))) == "0-55/5"
    assert compact_values([1, 2, 3, 5]) == "1-3,5"
    assert compact_values([0, 30]) == "0,30"
    assert compact_values([7]) == "7"
