"""讓分盤的 **樣本外** 重測 (時序切分)。

執行: ``python3 analysis/validate_handicap_oos.py``

背景
----
2026-08-13 判定「讓分盤不可定價」時，用的是 **樣本內** 回測且
``dispersion_k = 6``。8/15 依大小分的樣本外驗證把 k 改成 14 ——
k 直接控制共享環境因子的離散程度，分差分布必然跟著變。
原結論建立在已經被換掉的參數上，因此必須重測。

這支腳本用與 `validate_oos.py` 相同的時序切分 (4-6 月配適、7 月後驗證)，
檢查模型的 **分差** 分布在結算整數上準不準。看板的 ``N±XX`` 正好結算在
整數 N 上，所以 P(分差 = n) 才是讓分盤唯一依賴的量。
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bethero.model import GameModel, NPBEnvironment, TeamInput
from config import calibration_2026 as cal
from analysis.validate_oos import SPLIT, fit, load_games

_C: dict = {}
_orig = GameModel._gamma_nodes
GameModel._gamma_nodes = lambda self, n=48: _C.setdefault(
    (self.env.dispersion_k, n), _orig(self, n))


def run_for(k: float, train, test, off, dfn, pf, lg, home):
    env = NPBEnvironment(league_rpg=lg, dispersion_k=k, home_edge=home,
                         extras_resolve_rate=cal.EXTRAS_RESOLVE_RATE)
    agg: dict = defaultdict(float)
    used = 0
    for g in test:
        if g["home"] not in off or g["place"] not in pf:
            continue
        d = GameModel(home=TeamInput(g["home"], off[g["home"]], dfn[g["home"]]),
                      away=TeamInput(g["away"], off[g["away"]], dfn[g["away"]]),
                      env=env, park_factor=pf[g["place"]]).distributions()
        used += 1
        for m, p in d.margin_pmf.items():
            agg[m] += p
    return agg, used


def main() -> None:
    games = load_games()
    train = [g for g in games if g["date"] < SPLIT]
    test = [g for g in games if g["date"] >= SPLIT]
    lg, home, off, dfn, pf = fit(train)

    obs: dict = defaultdict(int)
    n = 0
    for g in test:
        if g["home"] not in off or g["place"] not in pf:
            continue
        obs[g["hs"] - g["as"]] += 1
        n += 1

    print("# 讓分盤的樣本外重測\n")
    print(f"- 訓練 {len(train)} 場、驗證 **{n} 場**（模型沒看過）")
    print(f"- 對照: 2026-08-13 的原始判定是 **樣本內** 且 k=6\n")

    print("## P(分差 = n) —— 看板 N±XX 的結算點\n")
    print("| 分差 n | 實際 | 模型 k=6 | 差 | 模型 k=14 | 差 |")
    print("|---|---|---|---|---|---|")
    res = {}
    for k in (6.0, 14.0):
        res[k], used = run_for(k, train, test, off, dfn, pf, lg, home)
    worst = {6.0: 0.0, 14.0: 0.0}
    for m in range(-3, 4):
        ob = obs[m] / n
        row = f"| {m:+d} | {ob:.4f} "
        for k in (6.0, 14.0):
            mo = res[k][m] / used
            worst[k] = max(worst[k], abs(mo - ob))
            row += f"| {mo:.4f} | {mo - ob:+.4f} "
        print(row + "|")
    print(f"\n關鍵點最大偏離: k=6 **{worst[6.0]:.4f}**、k=14 **{worst[14.0]:.4f}**")

    print("\n## 一分差與和局比例\n")
    print("| 指標 | 實際 | k=6 | k=14 |")
    print("|---|---|---|---|")
    ob1 = sum(c for m, c in obs.items() if abs(m) == 1) / n
    ob0 = obs[0] / n
    r1 = {k: sum(p for m, p in res[k].items() if abs(m) == 1) / used for k in res}
    r0 = {k: res[k][0] / used for k in res}
    print(f"| 一分差 | {ob1:.4f} | {r1[6.0]:.4f} | {r1[14.0]:.4f} |")
    print(f"| 和局 | {ob0:.4f} | {r0[6.0]:.4f} | {r0[14.0]:.4f} |")

    se = (0.25 / n) ** 0.5
    print(f"\n{n} 場的二項標準誤約 {se:.4f}。")
    print("\n## 判定\n")
    for k in (6.0, 14.0):
        verdict = ("仍不可用（誤差遠大於 3pp 優勢門檻）"
                   if worst[k] > 0.03 else "誤差已降到門檻以下，可重新評估")
        print(f"- k={k:.0f}: 最大偏離 {worst[k]:.4f} → **{verdict}**")


if __name__ == "__main__":
    main()
