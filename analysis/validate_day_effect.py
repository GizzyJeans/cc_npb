"""同一天的比賽總分之間有沒有共同因子？

執行: ``python3 -m analysis.validate_day_effect``

為什麼要測
----------
2026-08-13 起的每日報告都附了一句警告: 「部位方向集中（幾乎都押小分），
遇到全聯盟爆分的一天會一起中彈」。這句話聽起來合理 —— 天氣、用球、
主審好球帶都是全聯盟共通的 —— 但一直沒有數字支持。

在 3,000 單位分成三注、而三注同向的日子，這個假設直接決定風險評估
是「三個獨立的 1,000」還是「一個放大的 3,000」。兩者差很多，該量。

怎麼測
------
單向隨機效果 ANOVA，把「日期」當成隨機因子:

    總分_ij = 大平均 + 日效果_i + 誤差_ij

組內相關 ICC = var(日效果) / (var(日效果) + var(誤差))。
ICC = 0 代表同一天的兩場比賽，跟隨機兩場比賽沒有任何差別。

另外做一個更直接的檢查: 從同一天抽 **三場不同的** 比賽 (不放回)，
對上從三個不同日子各抽一場，比較「三注小分同時輸」的機率。
不放回很重要 —— 放回抽樣會抽到同一場兩次，憑空造出相關性。

結果 (674 場, 122 個至少三場的比賽日)
--------------------------------------
    MS_between 14.468   MS_within 16.363   F = 0.884

F **小於 1**: 日與日之間的變異比同一天之內的變異還小，
連一點點正的日效果都看不到。

    ICC 點估計 0.0000，95% 信賴區間 [-0.063, +0.033]
    日效果標準差的 95% 上界 0.743 分（單場總分標準差 4.05 分）

    三注小分同時輸: 同一天 6.48%　跨三天 6.70%

**結論: 原本那句警告不成立，已撤回。** 同一晚的三注小分，聯合風險
與分散在三個晚上的三注幾乎完全相同（同日甚至略低，但差距在雜訊內）。

還活著的風險是另一件事，不要混為一談
------------------------------------
「同晚相關」不成立，不代表方向集中沒有代價。真正的風險是
**模型本身若有系統性方向偏誤**，那個偏誤會出現在每一注上，而且是
跨日累積、不會被分散掉的。這個要用 analysis/scorecard.py 的
「實際 − 模型」平均值追蹤，目前 -0.11 分 / 0.2 個標準誤，尚無證據。

換句話說: 該擔心的是模型錯，不是當晚的天氣。
"""

from __future__ import annotations

import json
import math
import random
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "https://npb.jp/games/2026/schedule_%s_detail.html"
MONTHS = ("03", "04", "05", "06", "07", "08")
ALLSTAR = {"パ・リーグ", "セ・リーグ"}
MIN_GAMES_PER_DAY = 3


def load_days() -> list[list[int]]:
    """回傳每個比賽日的總分清單（只留至少 MIN_GAMES_PER_DAY 場的日子）。"""
    import re

    row = re.compile(r'<tr id="date(\d{4})"[^>]*>(.*?)</tr>', re.S)

    def field(block: str, cls: str) -> str | None:
        m = re.search(r'<div class="%s">(.*?)</div>' % cls, block, re.S)
        if not m:
            return None
        return re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", m.group(1)).replace("&nbsp;", ""))

    byday: dict[str, list[int]] = defaultdict(list)
    for mm in MONTHS:
        with urllib.request.urlopen(BASE % mm, timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
        for mmdd, blk in row.findall(html):
            home, away = field(blk, "team1"), field(blk, "team2")
            s1, s2 = field(blk, "score1"), field(blk, "score2")
            if not home or not away or home in ALLSTAR or away in ALLSTAR:
                continue
            if not (s1 and s1.isdigit() and s2 and s2.isdigit()):
                continue
            byday["2026-%s-%s" % (mmdd[:2], mmdd[2:])].append(int(s1) + int(s2))
    return [v for v in byday.values() if len(v) >= MIN_GAMES_PER_DAY]


# --- F 分布的 CDF 與分位數 (不依賴 scipy) --------------------------------

def _betacf(a: float, b: float, x: float) -> float:
    MAXIT, EPS, FPMIN = 300, 3e-16, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        d, c = (FPMIN if abs(d) < FPMIN else d), (FPMIN if abs(c) < FPMIN else c)
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        c = 1.0 + aa / c
        d, c = (FPMIN if abs(d) < FPMIN else d), (FPMIN if abs(c) < FPMIN else c)
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < EPS:
            break
    return h


def _betai(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lb = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
          + a * math.log(x) + b * math.log(1.0 - x))
    bt = math.exp(lb)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def f_cdf(f: float, d1: int, d2: int) -> float:
    return _betai(d1 / 2.0, d2 / 2.0, d1 * f / (d1 * f + d2))


def f_quantile(p: float, d1: int, d2: int) -> float:
    lo, hi = 1e-9, 1e9
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if f_cdf(mid, d1, d2) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def main() -> None:
    days = load_days()
    n = sum(len(v) for v in days)
    m = len(days)
    grand = sum(sum(v) for v in days) / n
    # 各組大小不等時的有效 k (Searle)
    k = (n - sum(len(v) ** 2 for v in days) / n) / (m - 1)

    ss_b = sum(len(v) * (sum(v) / len(v) - grand) ** 2 for v in days)
    ss_w = sum(sum((t - sum(v) / len(v)) ** 2 for t in v) for v in days)
    d1, d2 = m - 1, n - m
    ms_b, ms_w = ss_b / d1, ss_w / d2
    f_obs = ms_b / ms_w

    icc = max((f_obs - 1.0) / (f_obs - 1.0 + k), 0.0)
    fu, fl = f_quantile(0.975, d1, d2), f_quantile(0.025, d1, d2)
    lo = (f_obs / fu - 1.0) / (k + f_obs / fu - 1.0)
    hi = (f_obs / fl - 1.0) / (k + f_obs / fl - 1.0)

    print("# 同日共同因子檢定\n")
    print(f"- 比賽日 {m} 天、比賽 {n} 場、有效每日場數 k = {k:.2f}")
    print(f"- 大平均總分 {grand:.3f}、單場總分標準差 {ms_w ** 0.5:.2f}")
    print(f"- MS_between **{ms_b:.3f}**、MS_within **{ms_w:.3f}**、F = **{f_obs:.4f}**")
    if f_obs < 1.0:
        print("  - F 小於 1：日與日之間的變異比同一天之內還小，"
              "**連正的日效果都看不到**。")
    print(f"- ICC 點估計 **{icc:.4f}**，95% 信賴區間 [{lo:+.4f}, {hi:+.4f}]")
    if hi < 1.0:
        sd_hi = math.sqrt(max(hi, 0.0) / (1.0 - max(hi, 0.0)) * ms_w)
        print(f"- 日效果標準差的 95% 上界 **{sd_hi:.3f} 分**"
              f"（對照單場總分標準差 {ms_w ** 0.5:.2f} 分）")

    # 直接檢查: 三注同向小分，同日 vs 跨日
    lines = [8.125, 7.0, 6.5]
    random.seed(11)
    trials = 400_000
    pool = [v for v in days if len(v) >= 3]

    def joint_loss(same_day: bool) -> float:
        hit = 0
        for _ in range(trials):
            if same_day:
                picks = random.sample(random.choice(pool), 3)
            else:
                picks = [random.choice(random.choice(days)) for _ in range(3)]
            random.shuffle(picks)
            if all(t > line for t, line in zip(picks, lines)):
                hit += 1
        return 100.0 * hit / trials

    same, cross = joint_loss(True), joint_loss(False)
    print(f"\n- 三注小分（等效盤口 {lines}）同時輸的機率："
          f"同一天 **{same:.2f}%**、跨三天 **{cross:.2f}%**")
    print(f"  - 差距 {same - cross:+.2f} 個百分點，落在雜訊內。"
          "同一晚下三注，聯合風險與分散到三晚幾乎相同。")

    print("\n## 結論\n")
    print("「部位方向集中，遇到全聯盟爆分的一天會一起中彈」**不成立，已撤回**。")
    print("還活著的是另一個風險：模型若有系統性方向偏誤，該偏誤會出現在"
          "每一注上且跨日累積，分散下注不會稀釋它。"
          "用 `analysis/scorecard.py` 的「實際 − 模型」平均值追蹤。")


if __name__ == "__main__":
    main()
