"""Checks for the parts of build.py with real logic: streaks, wrapping and the inkey demo frames."""

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build


def days_from(counts, start="2026-10-01"):
    first = dt.date.fromisoformat(start)
    return [{"date": (first + dt.timedelta(days=index)).isoformat(), "count": count} for index, count in enumerate(counts)]


def test_streaks():
    days = days_from([1, 1, 1, 0, 2, 3, 0])
    today = dt.date(2026, 10, 7)
    # Today has nothing yet, so the streak still counts up to yesterday
    assert build.streaks(days, today) == (2, 3)
    assert build.streaks(days_from([0, 0, 0]), dt.date(2026, 10, 3)) == (0, 0)
    assert build.streaks(days_from([0, 4, 4]), dt.date(2026, 10, 3)) == (2, 2)


def test_wrap():
    lines = build.wrap("one two three four five six seven", 16, 80)
    assert len(lines) > 1
    assert all(build.text_width(line, 16) <= 80 for line in lines)
    assert " ".join(lines) == "one two three four five six seven"


def test_demo_frames():
    frames = build.demo_frames([{"typed": "ghbdtn", "fixed": "привет"}, {"typed": "rfr", "fixed": "как"}])
    assert frames[0] == ("", "g", False)
    assert frames[6] == ("привет", "", True)
    assert frames[-1] == ("привет как", "", True)


if __name__ == "__main__":
    test_streaks()
    test_wrap()
    test_demo_frames()
    print("ok")
