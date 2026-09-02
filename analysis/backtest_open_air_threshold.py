"""露天 EV 門檻由 +7% 降回 +4% 的回溯檢驗。

執行: ``python3 -m analysis.backtest_open_air_threshold``

背景
----
2026-08-16 使用者決定: 露天球場不再因為缺天氣資料而直接封鎖，
改成要求更高的 EV (+7%，一般為 +4%)。理由是球場係數已內含該球場的
常態風況，缺的只是「今日偏離常態多少」—— 那是增加變異而非造成偏誤。

但 scorecard 從 2026-08-25 起持續追蹤這個門檻的依據，結果是:

    08-25  露天 +0.32 (n=25) vs 巨蛋 -0.03 (n=28)   差 +0.34，0.4 個標準誤
    08-26  露天 +0.35 (n=28) vs 巨蛋 +0.13 (n=31)   差 +0.22，0.2 個標準誤
    08-27  露天 +0.38 (n=31) vs 巨蛋 +0.38 (n=33)   差 +0.00，0.0 個標準誤
    09-01  露天 -0.08 (n=43) vs 巨蛋 +0.25 (n=45)   差 -0.33，0.4 個標準誤

**依據不只是消失，方向還翻負了** —— 露天的模型誤差反而比巨蛋小。
繼續維持 +7% 等於在對一個沒有證據的風險收費。

方法
----
關鍵是 **不用今天的校準重算**。config 這兩週改過十幾次，重算出來的 EV
不是當天實際看到的數字，那種「回溯」只會證明今天的模型看得懂今天的資料。

改成解析每日報告 (`analysis/2026-MM-DD.md`) 裡 **當時算出並據以決策的
EV 與門檻理由**，只做一件事: 把「唯一失敗原因是露天 +7% 門檻、
且 EV >= 4%」的場次改判為通過，其餘一律不動。

三個必須遵守的細節:

1. **只有「唯一失敗原因是 EV 門檻」才會翻。** 若理由裡還有
   「未達 3pp 門檻」或任何資料缺口，降門檻救不了它。
2. **資料完整度不足 (觀察) 的場次永遠不翻。** 降 EV 門檻不會補上缺的資料。
3. **必須重跑每日預算配置。** 單日上限 3,000 依 EV 由高到低配置，
   新增的部位可能把原本拿到額度的低 EV 部位擠掉 ——
   只把新部位的損益加上去是錯的。

適用範圍: 2026-08-16 (該政策上路日) 之後的比賽日。在那之前露天是
直接封鎖 (weather_known 未放棄)，反事實情境不同，不納入。
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

from bethero.lines import settle_total
from analysis.settle import LEDGER, payout

POLICY_START = "2026-08-16"
"""露天改用較高 EV 門檻的政策上路日。"""

NEW_MIN_EV = 4.0
"""降回的門檻 (百分點)。"""

OLD_MIN_EV = 7.0

REPORT_DIR = Path(__file__).resolve().parent

ROW = re.compile(
    r"^\|\s*\d+\s*\|\s*(?P<game>[^|]+?)\s*\|[^|]*\|[^|]*\|[^|]*\|[^|]*\|"
    r"\s*(?P<ev>[-+][\d.]+)%\s*\|\s*(?P<stake>[\d,]+)\s*\|[^|]*\|"
    r"\s*\*\*(?P<status>[^*]+)\*\*\s*\|",
    re.M,
)
REASON = re.compile(r"^\s+- (?P<game>.+?) — (?P<why>.+)$", re.M)


def parse_report(date: str) -> dict:
    """從當日報告取出每場的 EV、注碼、狀態與不下注理由。"""
    path = REPORT_DIR / f"{date}.md"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    out: dict[str, dict] = {}
    for m in ROW.finditer(text):
        out[m.group("game").strip()] = {
            "ev": float(m.group("ev")),
            "stake": float(m.group("stake").replace(",", "")),
            "status": m.group("status").strip(),
            "why": "",
        }
    # 「明確不建議下注」段落裡的理由
    block = text.split("**明確不建議下注的比賽**")
    if len(block) > 1:
        for m in REASON.finditer(block[1].split("\n\n")[0]):
            g = m.group("game").strip()
            if g in out:
                out[g]["why"] = m.group("why").strip()
    return out


def only_failed_open_air_ev(why: str) -> bool:
    """失敗理由是否 **只有** 露天 +7% 的 EV 門檻。

    理由字串以「；」分隔。只要還有第二個條款 (3pp 優勢門檻、
    任何資料缺口)，降 EV 門檻就救不了它。
    """
    clauses = [c.strip() for c in why.split("；") if c.strip()]
    return len(clauses) == 1 and re.fullmatch(
        r"EV [-+][\d.]+% 未達 \+7% 門檻", clauses[0]) is not None


def allocate(candidates: list[dict], budget: float) -> None:
    """依 EV 由高到低配置單日額度，超出的注碼歸零 (與 slate 的邏輯一致)。"""
    left = budget
    for c in sorted(candidates, key=lambda x: -x["ev"]):
        if c["qualified"] and left >= 1000.0 - 1e-9:
            c["new_stake"] = 1000.0
            left -= 1000.0
        else:
            c["new_stake"] = 0.0


def main() -> None:
    print("# 露天 EV 門檻 +7% → +4% 的回溯檢驗\n")
    print(f"- 適用範圍：{POLICY_START} 起（該政策上路日）之後的比賽日")
    print("- EV 取自 **當日報告實際算出的數字**，不是用今天的校準重算")
    print("- 只翻「唯一失敗原因是露天 +7% 門檻且 EV ≥ +4%」的場次")
    print("- 每日 3,000 額度 **重新配置**，新部位可能擠掉原本的低 EV 部位\n")

    rows = []
    unfunded = []
    old_total = new_total = 0.0
    old_staked = new_staked = 0.0

    for date in sorted(LEDGER):
        if date[:10] < POLICY_START:
            continue
        spec = LEDGER[date]
        slate = importlib.import_module(spec["module"])
        open_air = getattr(slate, "OPEN_AIR", set())
        if not hasattr(slate, "OPEN_AIR_MIN_EV"):
            continue
        report = parse_report(date)
        if not report:
            continue

        cands = []
        for game in slate.GAMES:
            key = game.matchup
            r = report.get(key)
            if r is None:
                continue
            sel, side, stake, hk, status = spec["positions"][game.home_team]
            final = spec["finals"][game.home_team]
            is_open = slate.PARK_KEY[game.venue] in open_air
            flips = (is_open and r["status"] == "不下注"
                     and r["ev"] >= NEW_MIN_EV
                     and only_failed_open_air_ev(r["why"]))
            cands.append({
                "date": date, "game": key, "ev": r["ev"], "side": side,
                "hk": hk, "old_stake": stake, "open_air": is_open,
                "qualified": r["status"] == "推薦" or flips,
                "flips": flips, "total": game.total,
                "final": None if final is None else sum(final),
            })

        allocate(cands, getattr(slate, "DAILY_BUDGET", 3000.0))

        for c in cands:
            if c["final"] is None:      # 中止退回本金，兩案相同
                continue
            ratio = settle_total(c["total"], c["final"], c["side"])
            c["old_pl"] = payout(ratio, c["old_stake"], c["hk"])
            c["new_pl"] = payout(ratio, c["new_stake"], c["hk"])
            old_total += c["old_pl"]
            new_total += c["new_pl"]
            old_staked += c["old_stake"]
            new_staked += c["new_stake"]
            if c["old_stake"] != c["new_stake"]:
                rows.append(c)
            elif c["flips"] and c["new_stake"] == 0:
                unfunded.append(c)

    print("## 受影響的部位\n")
    if not rows:
        print("（無）")
    else:
        print("| 日期 | 比賽 | EV | 露天 | 原注碼 | 新注碼 | 實際總分 | 原損益 | 新損益 |")
        print("|---|---|---|---|---|---|---|---|---|")
        for c in rows:
            kind = "露天" if c["open_air"] else "巨蛋"
            print(f"| {c['date'][5:]} | {c['game']} | {c['ev']:+.1f}% | {kind} "
                  f"| {c['old_stake']:,.0f} | {c['new_stake']:,.0f} | {c['final']} "
                  f"| {c['old_pl']:+,.0f} | {c['new_pl']:+,.0f} |")

    added = [c for c in rows if c["flips"] and c["new_stake"] > 0]
    pushed = [c for c in rows if not c["flips"] and c["new_stake"] == 0]
    print(f"\n- 新進場的露天部位 **{len(added)}** 個；"
          f"因額度被擠掉的原有部位 **{len(pushed)}** 個。")
    if added:
        w = sum(1 for c in added if c["new_pl"] > 0)
        print(f"  - 新進場的 {len(added)} 個裡 **{w} 贏 {len(added) - w} 輸**，"
              f"合計 {sum(c['new_pl'] for c in added):+,.0f}。")
    if pushed:
        print(f"  - 被擠掉的 {len(pushed)} 個原本合計 "
              f"{sum(c['old_pl'] for c in pushed):+,.0f}（正值代表這個改動讓我們錯過獲利）。")

    # 通過門檻但拿不到額度的 —— 這一段才看得出門檻與預算誰才是真正的約束
    starved = [c for c in unfunded if c["flips"]]
    if starved:
        print(f"\n## 通過新門檻但 **拿不到額度** 的場次（{len(starved)} 個）\n")
        print("| 日期 | 比賽 | EV | 實際總分 | 假設 1,000 單位 |")
        print("|---|---|---|---|---|")
        for c in starved:
            hypo = payout(settle_total(c["total"], c["final"], c["side"]), 1000.0, c["hk"])
            print(f"| {c['date'][5:]} | {c['game']} | {c['ev']:+.1f}% "
                  f"| {c['final']} | {hypo:+,.0f} |")
        print("\n- 這些場次即使把門檻降到 +4% 也 **不會下注** —— "
              "當天已經有三個 EV 更高的部位把 3,000 額度用完了。")
        print("- **真正的約束是單日額度，不是露天門檻。** 門檻只在"
              "「當天合格部位少於三個」時才會實際咬到。")

    print("\n## 總結\n")
    print("| 方案 | 下注金額 | 損益 | ROI |")
    print("|---|---|---|---|")
    for label, st, pl in (("維持 +7%", old_staked, old_total),
                          ("降回 +4%", new_staked, new_total)):
        roi = pl / st if st else 0.0
        print(f"| {label} | {st:,.0f} | {pl:+,.0f} | {roi:+.1%} |")
    print(f"\n- 損益差 **{new_total - old_total:+,.0f}**、"
          f"下注金額差 {new_staked - old_staked:+,.0f}。")

    n = len(added)
    print("\n## 解讀\n")
    if n == 0:
        print("- 這段期間 **沒有任何場次** 卡在 4-7% 之間且其他門檻全過，"
              "所以這個改動在歷史上不會有任何影響。"
              "它的價值全在未來，而依據是 scorecard 的露天/巨蛋誤差比較。")
    else:
        print(f"- 樣本只有 **{n} 個部位**，遠不足以判斷這個改動的優劣。"
              "決定要不要改，依據應該是 scorecard 的露天/巨蛋誤差比較"
              "（門檻的 *理由* 是否成立），而不是這 %d 注的輸贏。" % n)
        print("- 這份回溯的用途是 **量化改動的規模與方向**，不是驗證它會賺錢。")


if __name__ == "__main__":
    main()
