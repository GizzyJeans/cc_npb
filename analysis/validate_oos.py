"""大小分模型的 **樣本外** 驗證 (時序切分)。

執行: ``python3 analysis/validate_oos.py``

先前 `KNOWN_BIASES` 裡「大小分方向已驗證可用」那條，是拿同一批比賽
既配適又驗證的 —— 樣本內，只能算技巧的上界。這支腳本改成時序切分:

* 訓練: 開季 ~ 6/30，只用這段配適球隊/球場係數
* 驗證: 7/1 之後，模型完全沒看過

驗證兩件事:

1. **累積分布校準**: 模型說 P(總分 > n) = X%，實際是不是 X%。
   這是大小分定價唯一真正依賴的量。
2. **右偏是不是真的**: 不用模型，直接看「盤口設在該期間平均總分」時
   小分過盤的比例。這是所有小分推薦的根基 —— 若右偏不成立，
   整套大小分定價都要重來。
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bethero.model import GameModel, NPBEnvironment, TeamInput
from config import calibration_2026 as cal

SCRATCH = Path("/tmp/claude-0/-home-user-cc-npb/"
               "03e89d1b-2c9d-5056-843e-60ec8d7218dd/scratchpad")
SPLIT = "2026-07-01"
ALLSTAR = {"パ・リーグ", "セ・リーグ"}

_C: dict = {}
_orig = GameModel._gamma_nodes
GameModel._gamma_nodes = lambda self, n=48: _C.setdefault(
    (self.env.dispersion_k, n), _orig(self, n))


def load_games() -> list[dict]:
    games = json.load(open(SCRATCH / "season.json"))
    return [g for g in games
            if g["hs"] is not None and g["as"] is not None
            and g["home"] not in ALLSTAR and g["away"] not in ALLSTAR]


def fit(games: list[dict]):
    """只用傳入的比賽配適 off/def/park (與 derive_calibration_2026 同法)。"""
    teams = sorted({g["home"] for g in games} | {g["away"] for g in games})
    venues = sorted({g["place"] for g in games})
    n = len(games)
    lg = sum(g["hs"] + g["as"] for g in games) / (2 * n)
    home = (sum(g["hs"] for g in games) / sum(g["as"] for g in games)) ** 0.5
    off = {t: 1.0 for t in teams}
    dfn = {t: 1.0 for t in teams}
    pf = {v: 1.0 for v in venues}
    gc: dict = defaultdict(int)
    for g in games:
        gc[g["place"]] += 1
    for _ in range(200):
        num, den = defaultdict(float), defaultdict(float)
        for g in games:
            num[g["home"]] += g["hs"]
            den[g["home"]] += lg * dfn[g["away"]] * pf[g["place"]] * home
            num[g["away"]] += g["as"]
            den[g["away"]] += lg * dfn[g["home"]] * pf[g["place"]] / home
        off = {t: num[t] / den[t] for t in teams}
        num, den = defaultdict(float), defaultdict(float)
        for g in games:
            num[g["away"]] += g["hs"]
            den[g["away"]] += lg * off[g["home"]] * pf[g["place"]] * home
            num[g["home"]] += g["as"]
            den[g["home"]] += lg * off[g["away"]] * pf[g["place"]] / home
        dfn = {t: num[t] / den[t] for t in teams}
        num, den = defaultdict(float), defaultdict(float)
        for g in games:
            num[g["place"]] += g["hs"] + g["as"]
            den[g["place"]] += (lg * off[g["home"]] * dfn[g["away"]] * home
                                + lg * off[g["away"]] * dfn[g["home"]] / home)
        pf = {v: num[v] / den[v] for v in venues}
        mean = sum(pf[v] * gc[v] for v in venues) / n
        pf = {v: pf[v] / mean for v in venues}
    # 收縮 (同 config: 只用 >=20 場的球場估真實變異)
    sd = (sum((g["hs"] + g["as"] - 2 * lg) ** 2 for g in games) / n) ** 0.5
    noise = {v: (sd / gc[v] ** 0.5 / (2 * lg)) ** 2 for v in pf}
    primary = [v for v in pf if gc[v] >= 20]
    w = sum(gc[v] for v in primary)
    m = sum(pf[v] * gc[v] for v in primary) / w
    var_obs = sum(gc[v] * (pf[v] - m) ** 2 for v in primary) / w
    var_noise = sum(gc[v] * noise[v] for v in primary) / w
    var_true = max(var_obs - var_noise, 1e-6)
    pf = {v: m + (pf[v] - m) * (var_true / (var_true + noise[v])) for v in pf}
    return lg, home, off, dfn, pf


def main() -> None:
    games = load_games()
    train = [g for g in games if g["date"] < SPLIT]
    test = [g for g in games if g["date"] >= SPLIT]
    print("# 大小分模型的樣本外驗證（時序切分）\n")
    print(f"- 訓練: {min(g['date'] for g in train)} ~ "
          f"{max(g['date'] for g in train)}，**{len(train)} 場**")
    print(f"- 驗證: {min(g['date'] for g in test)} ~ "
          f"{max(g['date'] for g in test)}，**{len(test)} 場**（模型完全沒看過）\n")

    lg, home, off, dfn, pf = fit(train)
    print(f"訓練期聯盟每隊每場得分 {lg:.4f}（全季 {cal.LEAGUE_RPG:.4f}）、"
          f"主場乘數 {home:.4f}\n")

    env = NPBEnvironment(league_rpg=lg, dispersion_k=cal.DISPERSION_K,
                         home_edge=home,
                         extras_resolve_rate=cal.EXTRAS_RESOLVE_RATE)

    agg: dict = defaultdict(float)
    used = 0
    preds = []
    for g in test:
        if (g["home"] not in off or g["away"] not in off
                or g["place"] not in pf):
            continue        # 驗證期出現訓練期沒有的球場
        d = GameModel(home=TeamInput(g["home"], off[g["home"]], dfn[g["home"]]),
                      away=TeamInput(g["away"], off[g["away"]], dfn[g["away"]]),
                      env=env, park_factor=pf[g["place"]]).distributions()
        used += 1
        preds.append((d, g["hs"] + g["as"]))
        for t, p in d.total_pmf.items():
            agg[t] += p

    obs: dict = defaultdict(int)
    for _, actual in preds:
        obs[actual] += 1

    print(f"## 1. 累積分布校準（樣本外 {used} 場）\n")
    print("| 門檻 n | 模型 P(總分>n) | 實際 | 差 |")
    print("|---|---|---|---|")
    worst = 0.0
    for t in (4, 5, 6, 7, 8, 9, 10):
        mo = sum(p for tt, p in agg.items() if tt > t) / used
        ob = sum(c for tt, c in obs.items() if tt > t) / used
        worst = max(worst, abs(mo - ob))
        print(f"| {t} | {mo:.4f} | {ob:.4f} | {mo - ob:+.4f} |")
    print(f"\n最大偏離 **{worst:.4f}**（樣本內回測時是 0.01 以內）。")
    se = (0.25 / used) ** 0.5
    print(f"{used} 場的二項標準誤約 {se:.4f}，因此 {worst / se:.1f} 個標準誤。")

    mp = sum(d.expected_total() for d, _ in preds) / used
    ma = sum(a for _, a in preds) / used
    print(f"\n平均: 模型 {mp:.3f} vs 實際 {ma:.3f}（{mp - ma:+.3f}）")

    print("\n## 2. 右偏是不是真的（不用模型，純看資料）\n")
    print("關鍵是盤口要 **設在該期間的平均值上**。把平均四捨五入到整數會把"
          "「線在哪」和「分布形狀」混在一起 —— 驗證期平均 7.47，設在 7 等於"
          "先讓大分佔便宜。這裡改用半球盤（不走盤）設在平均值。\n")
    print("| 期間 | 場數 | 平均總分 | 半球盤設在平均 | 小分過盤率 |")
    print("|---|---|---|---|---|")
    for label, sample in (("訓練期", train), ("驗證期", test)):
        n = len(sample)
        mean = sum(g["hs"] + g["as"] for g in sample) / n
        under = sum(1 for g in sample if g["hs"] + g["as"] < mean)
        print(f"| {label} | {n} | {mean:.3f} | {mean:.3f} | **{under / n:.4f}** |")
    print("\n以 0.930 對 0.930 計算，損益兩平需要 51.81%。"
          "右偏若成立，這個比例應該穩定高於 0.5。")

    print("\n## 3. 是「水位」還是「形狀」錯？\n")
    print("把模型的得分水位強制校到驗證期的實際平均，再看累積分布還準不準。"
          "若校平之後就吻合 => 只是賽季中得分環境上移（可修）；"
          "若仍偏離 => 分布形狀本身錯（整套定價要重來）。\n")
    scale = ma / mp
    agg2: dict = defaultdict(float)
    for g in test:
        if (g["home"] not in off or g["away"] not in off
                or g["place"] not in pf):
            continue
        m = GameModel(home=TeamInput(g["home"], off[g["home"]], dfn[g["home"]]),
                      away=TeamInput(g["away"], off[g["away"]], dfn[g["away"]]),
                      env=env, park_factor=pf[g["place"]] * scale)
        for t, p in m.distributions().total_pmf.items():
            agg2[t] += p
    print(f"（水位校正倍率 {scale:.4f}）\n")
    print("| 門檻 n | 校平後模型 | 實際 | 差 |")
    print("|---|---|---|---|")
    worst2 = 0.0
    for t in (4, 5, 6, 7, 8, 9, 10):
        mo = sum(p for tt, p in agg2.items() if tt > t) / used
        ob = sum(c for tt, c in obs.items() if tt > t) / used
        worst2 = max(worst2, abs(mo - ob))
        print(f"| {t} | {mo:.4f} | {ob:.4f} | {mo - ob:+.4f} |")
    print(f"\n校平後最大偏離 **{worst2:.4f}**（校平前 {worst:.4f}）。")
    print("→ " + ("水位是主因，形狀大致可用。" if worst2 < worst / 2
                 else "校平後仍明顯偏離，**形狀本身也有問題**。"))

    print("\n## 4. 可靠度曲線（模型說幾成，實際就是幾成？）\n")
    rows = []
    for d, actual in preds:
        line = round(d.expected_total())      # 盤口設在模型自己的預期值
        p_under = sum(p for t, p in d.total_pmf.items() if t < line)
        p_push = sum(p for t, p in d.total_pmf.items() if t == line)
        if 1 - p_push <= 1e-9:
            continue
        rows.append((p_under / (1 - p_push), actual, line))
    rows.sort()
    B = 4
    size = len(rows) // B
    print("| 分組 | 場數 | 模型平均小分機率 | 實際小分過盤率 |")
    print("|---|---|---|---|")
    for i in range(B):
        chunk = rows[i * size:(i + 1) * size] if i < B - 1 else rows[i * size:]
        pm = sum(r[0] for r in chunk) / len(chunk)
        dec = [r for r in chunk if r[1] != r[2]]
        act = sum(1 for r in dec if r[1] < r[2]) / len(dec) if dec else float("nan")
        print(f"| 第 {i + 1} 組 | {len(chunk)} | {pm:.4f} | {act:.4f} |")
    allp = sum(r[0] for r in rows) / len(rows)
    dec = [r for r in rows if r[1] != r[2]]
    alla = sum(1 for r in dec if r[1] < r[2]) / len(dec)
    print(f"| **全部** | {len(rows)} | **{allp:.4f}** | **{alla:.4f}** |")
    print(f"\n盤口設在模型預期值時，模型說小分過盤 {allp:.1%}、實際 {alla:.1%}。")


if __name__ == "__main__":
    main()
