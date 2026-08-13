"""從 npb.jp 重新推導 `config/calibration_2026.py` 的每一個數字。

執行: ``python3 analysis/derive_calibration_2026.py``  (需要能連上 npb.jp)

這支腳本存在的理由: `config/calibration_2026.py` 是一整面數字，
沒有這支腳本就無法覆核。它會重新抓資料、重算、並把結果跟目前寫死在
config 裡的值比對，不一致就報錯。

步驟
----
1. 抓 2026 年 3-8 月的賽程頁，解析出每一場的主客隊、比分、球場。
2. 用官方球隊打擊表的「得点」欄交叉驗證解析結果 (應 12/12 相符)。
3. 迭代比例配適，同時解出球隊進攻/守備係數與球場係數。
4. 球場係數做逐球場的經驗貝氏收縮。
5. 印出與 config 的差異。
"""

from __future__ import annotations

import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import calibration_2026 as cal

BASE = "https://npb.jp"
MONTHS = ("03", "04", "05", "06", "07", "08")
ALLSTAR = {"パ・リーグ", "セ・リーグ"}
ROW = re.compile(r'<tr id="date(\d{4})"[^>]*>(.*?)</tr>', re.S)


def fetch(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def field(block: str, cls: str) -> str | None:
    m = re.search(r'<div class="%s">(.*?)</div>' % cls, block, re.S)
    if not m:
        return None
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", m.group(1)).replace("&nbsp;", ""))


def load_games() -> list[dict]:
    seen, games = set(), []
    for mm in MONTHS:
        html = fetch(f"{BASE}/games/2026/schedule_{mm}_detail.html")
        for mmdd, blk in ROW.findall(html):
            home, away = field(blk, "team1"), field(blk, "team2")
            if not home or not away or home in ALLSTAR or away in ALLSTAR:
                continue
            hs, as_ = field(blk, "score1"), field(blk, "score2")
            if not (hs and hs.isdigit() and as_ and as_.isdigit()):
                continue          # 未開打或中止
            key = (mmdd, home, away)
            if key in seen:
                continue
            seen.add(key)
            games.append({"home": home, "away": away, "hs": int(hs),
                          "as": int(as_), "place": field(blk, "place")})
    return games


def official_runs() -> dict[str, int]:
    """官方球隊打擊表的「得点」欄，用來驗證比分解析。"""
    out = {}
    for page in ("tmb_c", "tmb_p"):
        html = fetch(f"{BASE}/bis/2026/stats/{page}.html")
        for r in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
            c = [re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", x)).replace("&nbsp;", "")
                 for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)]
            if len(c) > 6 and c[0] != "チーム" and c[5].isdigit():
                out[c[0]] = int(c[5])
    return out


def fit(games: list[dict]) -> tuple[dict, dict, dict, float, float]:
    teams = sorted({g["home"] for g in games} | {g["away"] for g in games})
    venues = sorted({g["place"] for g in games})
    n = len(games)
    lg = sum(g["hs"] + g["as"] for g in games) / (2 * n)
    home_edge = (sum(g["hs"] for g in games) / sum(g["as"] for g in games)) ** 0.5

    off = {t: 1.0 for t in teams}
    dfn = {t: 1.0 for t in teams}
    pf = {v: 1.0 for v in venues}
    gcount = defaultdict(int)
    for g in games:
        gcount[g["place"]] += 1

    for _ in range(300):
        num, den = defaultdict(float), defaultdict(float)
        for g in games:
            num[g["home"]] += g["hs"]
            den[g["home"]] += lg * dfn[g["away"]] * pf[g["place"]] * home_edge
            num[g["away"]] += g["as"]
            den[g["away"]] += lg * dfn[g["home"]] * pf[g["place"]] / home_edge
        off = {t: num[t] / den[t] for t in teams}

        num, den = defaultdict(float), defaultdict(float)
        for g in games:
            num[g["away"]] += g["hs"]
            den[g["away"]] += lg * off[g["home"]] * pf[g["place"]] * home_edge
            num[g["home"]] += g["as"]
            den[g["home"]] += lg * off[g["away"]] * pf[g["place"]] / home_edge
        dfn = {t: num[t] / den[t] for t in teams}

        num, den = defaultdict(float), defaultdict(float)
        for g in games:
            num[g["place"]] += g["hs"] + g["as"]
            den[g["place"]] += (lg * off[g["home"]] * dfn[g["away"]] * home_edge
                                + lg * off[g["away"]] * dfn[g["home"]] / home_edge)
        pf = {v: num[v] / den[v] for v in venues}
        mean = sum(pf[v] * gcount[v] for v in venues) / n
        pf = {v: pf[v] / mean for v in venues}

    return off, dfn, pf, lg, home_edge


def shrink(pf: dict, games: list[dict], lg: float) -> dict:
    """逐球場的經驗貝氏收縮; 真實變異只用 >=40 場的主要球場估。"""
    n = len(games)
    gcount = defaultdict(int)
    for g in games:
        gcount[g["place"]] += 1
    sd = (sum((g["hs"] + g["as"] - 2 * lg) ** 2 for g in games) / n) ** 0.5
    noise = {v: (sd / gcount[v] ** 0.5 / (2 * lg)) ** 2 for v in pf}
    primary = [v for v in pf if gcount[v] >= 40]
    w = sum(gcount[v] for v in primary)
    m = sum(pf[v] * gcount[v] for v in primary) / w
    var_obs = sum(gcount[v] * (pf[v] - m) ** 2 for v in primary) / w
    var_noise = sum(gcount[v] * noise[v] for v in primary) / w
    var_true = max(var_obs - var_noise, 1e-6)
    return {v: m + (pf[v] - m) * (var_true / (var_true + noise[v])) for v in pf}


def main() -> int:
    games = load_games()
    print(f"解析到 {len(games)} 場已完成的例行賽")

    rs = defaultdict(int)
    for g in games:
        rs[g["home"]] += g["hs"]
        rs[g["away"]] += g["as"]
    official = official_runs()
    bad = [t for t in rs if t in official and rs[t] != official[t]]
    print("與官方「得点」欄比對: %d/%d 相符" % (len(rs) - len(bad), len(rs)))
    if bad:
        print("!! 不符:", {t: (rs[t], official[t]) for t in bad})
        return 1

    off, dfn, pf_raw, lg, home_edge = fit(games)
    pf = shrink(pf_raw, games, lg)

    print(f"\nleague_rpg {lg:.4f}  (config {cal.LEAGUE_RPG})")
    print(f"home_edge  {home_edge:.4f}  (config {cal.HOME_EDGE})")

    print("\n%-16s %9s %9s %8s" % ("球場", "重算", "config", "差"))
    worst = 0.0
    for v, want in sorted(cal.PARK_FACTORS_2026.items(), key=lambda kv: -kv[1]):
        got = pf.get(v)
        if got is None:
            print("%-16s %9s" % (v, "缺"))
            continue
        worst = max(worst, abs(got - want))
        print("%-16s %9.4f %9.4f %+8.4f" % (v, got, want, got - want))

    print("\n%-10s %9s %9s %8s" % ("球隊", "重算 off", "config", "差"))
    for t, want in sorted(cal.TEAM_OFFENCE.items(), key=lambda kv: -kv[1]):
        got = off[t]
        worst = max(worst, abs(got - want))
        print("%-10s %9.4f %9.4f %+8.4f" % (t, got, want, got - want))

    print("\n最大差異 %.4f" % worst)
    if worst > 0.02:
        print("!! 與 config 的差異超過容忍值 —— 賽季有新比賽，請更新 config")
        return 1
    print("與 config 一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
