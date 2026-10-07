"""校準只吃例行賽: 任一隊打滿 143 場之後的比賽（季後賽）要排除。"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "refresh_calibration",
    Path(__file__).resolve().parent.parent / "scripts" / "refresh_calibration.py")
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)


def _g(date, home, away):
    return {"date": date, "home": home, "away": away, "hs": 1, "as": 0, "park": "x"}


def test_games_after_a_team_reaches_the_cap_are_dropped():
    games = [_g(f"2026-09-{d:02d}", "巨人", "DeNA") for d in range(1, 5)]
    games.append(_g("2026-10-10", "巨人", "DeNA"))          # 季後賽
    kept = rc.cap_regular_season(games, n=4)
    assert len(kept) == 4
    assert all(g["date"] < "2026-10-10" for g in kept)


def test_cap_applies_if_either_team_is_full():
    games = [_g("2026-09-01", "巨人", "DeNA"),
             _g("2026-09-02", "巨人", "DeNA"),
             _g("2026-09-03", "西武", "巨人")]               # 巨人 已滿 2 場
    kept = rc.cap_regular_season(games, n=2)
    assert [g["date"] for g in kept] == ["2026-09-01", "2026-09-02"]


def test_unsorted_input_is_capped_in_date_order():
    games = [_g("2026-10-10", "巨人", "DeNA"),
             _g("2026-09-01", "巨人", "DeNA")]
    kept = rc.cap_regular_season(games, n=1)
    assert [g["date"] for g in kept] == ["2026-09-01"]


def test_default_is_143():
    assert rc.REGULAR_SEASON_GAMES == 143
