"""從 npb.jp 重新配適整季校準值，並寫回 ``config/calibration_2026.py``。

執行::

    python3 scripts/refresh_calibration.py            # 抓取 + 配適 + 寫檔
    python3 scripts/refresh_calibration.py --dry-run  # 只印出，不寫檔

為什麼這支腳本要存在
--------------------
在 2026-09-15 之前，這條管線只以散落的腳本活在 scratchpad 裡。
2026-09-13 容器回收時它整個消失，於是 9/13 和 9/14 兩天的定價都只能
沿用 9/11 的球隊／球場／牛棚係數 —— 每天差一點，但缺口會累積。
把它收進版控就不會再發生。

方法
----
1. **逐場比分** 由 ``schedule_MM_detail.html`` 解析（3-9 月）。
   每列的第一格是 ``主隊 比分 - 比分 客隊``，第二格是 ``球場 時間``。
2. **迭代比例配適 (IPF)** 同時解出球隊進攻／守備與球場係數:

       E[A 隊對 B 隊在球場 v 的得分] = lg × off_A × def_B × PF_v × homeEdge^(±1)

   直接用 RS/G 會把球場混進球隊實力，所以下游一律用這裡的球場中性係數。
3. **球場係數做經驗貝氏收縮**: 只用場次 >= `PRIMARY_MIN_GAMES` 的主要球場
   估真實變異，每座球場依自己的場次數收縮 w_v = var_true/(var_true+noise_v)。
4. **牛棚係數** 由個人投手成績算: 單場平均局數 < 3 局者視為救援，
   合計失分率做球場曝險調整與收縮。

⚠️ 中性場地
-----------
地方球場（秋田、盛岡、ほっと神戸…）場次太少，係數不可用。它們會進入
配適（不丟資料），但 **不寫進 `PARK_FACTORS_2026`** —— 下游的
``park_factor()`` 查不到就退回中性值 1.0，並把 `park_factor_known` 記為 False。

⚠️ 這是重寫版，不是原管線的還原 —— 9/15 有一道接縫
--------------------------------------------------
原始腳本已隨容器消失，本檔是依方法重寫的。用 ``--through 2026-09-11``
跑回歸驗證（與已提交的 757 場校準比對）:

    LEAGUE_RPG   3.6057  vs  3.6057   **完全相同**
    HOME_EDGE    1.0220  vs  1.0220   **完全相同**

聯盟層級的兩個值分毫不差，代表 IPF 核心是等價的。球場係數則有小幅差異，
集中在收縮那一步（兩端的球場差最多）:

    神宮        1.2079  vs  1.1968   +0.9%   <- 最大
    甲子園       0.8428  vs  0.8541   -1.3%   <- 最大
    京セラD大阪    0.8594  vs  0.8645   -0.6%
    其餘 9 座    差距皆在 0.1-0.5% 之內
    牛棚係數     差距約 1%（例如巨人 0.8069 vs 0.8166）

差異遠小於單場總分標準差 4.0，但 **它是真實的，不是捨入誤差**。
因此 2026-09-15 起的校準序列與之前有一道接縫，回頭比對歷史數字時要知道。

採用它的理由: 舊管線已經不存在，而「停在 9/11 不動」比 1% 的接縫更糟。
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "calibration_2026.py"
CACHE = Path("/tmp/npb_cal_cache")

MONTHS = ("03", "04", "05", "06", "07", "08", "09")
TEAMS = ("ソフトバンク", "日本ハム", "オリックス", "ロッテ", "西武", "楽天",
         "阪神", "DeNA", "巨人", "中日", "広島", "ヤクルト")
CODES = {"g": "巨人", "t": "阪神", "db": "DeNA", "s": "ヤクルト", "d": "中日",
         "c": "広島", "h": "ソフトバンク", "f": "日本ハム", "l": "西武",
         "b": "オリックス", "e": "楽天", "m": "ロッテ"}

# 賽程頁的球場寫法 -> 正式名。含全形空白的寫法（神 宮／横 浜）先去空白再比對。
PARK_ALIASES = {
    "神宮": "神宮", "横浜": "横浜", "甲子園": "甲子園", "東京ドーム": "東京ドーム",
    "バンテリンドーム": "バンテリンドーム", "マツダ": "マツダスタジアム",
    "ベルーナドーム": "ベルーナドーム", "京セラD大阪": "京セラD大阪",
    "みずほPayPay": "みずほPayPay", "ZOZOマリン": "ZOZOマリン",
    "楽天モバイル": "楽天モバイル", "エスコン": "エスコンＦ",
}

PRIMARY_MIN_GAMES = 20
"""場次少於此數的球場，係數不可用，不寫進 PARK_FACTORS_2026。"""

SHRINK_IP = 60.0
"""個別投手（含牛棚合計）向聯盟平均回歸的局數。"""

RELIEF_IP_PER_GAME = 3.0
"""單場平均局數低於此值視為救援投手。"""


def fetch(url: str, name: str, refresh: bool) -> str:
    CACHE.mkdir(exist_ok=True)
    path = CACHE / name
    if path.exists() and not refresh:
        return path.read_text(encoding="utf-8", errors="replace")
    with urllib.request.urlopen(url, timeout=60) as r:
        text = r.read().decode("utf-8", errors="replace")
    path.write_text(text, encoding="utf-8")
    return text


def cells(tr: str) -> list[str]:
    return [re.sub(r"\s+", "", re.sub(r"<[^>]+>", "|", c)).strip("|")
            for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, flags=re.S)]


def parse_games(refresh: bool) -> list[dict]:
    """逐場比分。回傳 [{date, home, away, hs, as, park}]，只含已打完的例行賽。

    列的結構是 ``主隊|比分|-|比分|客隊`` 與 ``球場|時間|&nbsp;``，
    日期在 ``<tr id="dateMMDD">`` 上（同一天的第二場之後 id 是空的，
    所以要沿用上一個看到的日期）。
    """
    out = []
    row = re.compile(r"^(\S+?)\|+(\d+)\|+-\|+(\d+)\|+(\S+)$")
    for m in MONTHS:
        html = fetch(f"https://npb.jp/games/2026/schedule_{m}_detail.html",
                     f"sched_{m}.html", refresh)
        date = ""
        for tr_open, tr in re.findall(r"<tr([^>]*)>(.*?)</tr>", html, flags=re.S):
            hit_date = re.search(r'id="date(\d{4})"', tr_open)
            if hit_date:
                date = f"2026-{hit_date.group(1)[:2]}-{hit_date.group(1)[2:]}"
            c = cells(tr)
            if len(c) < 2:
                continue
            hit = row.match(c[0])
            if not hit:
                continue
            home, hs, as_, away = hit.group(1), int(hit.group(2)), \
                int(hit.group(3)), hit.group(4)
            if home not in TEAMS or away not in TEAMS:
                continue                       # 明星賽、二軍等
            # 第二格是「球場|時間|&nbsp;」—— 只取第一段，否則同一座球場會
            # 因為開賽時間不同而被拆成好幾個 key（ほっと神戸 16:00 / 18:00）。
            venue = c[1].split("|")[0]
            park = next((v for k, v in PARK_ALIASES.items() if k in venue), venue)
            out.append({"date": date, "home": home, "away": away,
                        "hs": hs, "as": as_, "park": park})
    return out


def fit(games: list[dict], rounds: int = 400) -> dict:
    """迭代比例配適: lg × off × def × PF × homeEdge^(±1)。"""
    n = len(games)
    lg = sum(g["hs"] + g["as"] for g in games) / (2 * n)
    off = {t: 1.0 for t in TEAMS}
    dfn = {t: 1.0 for t in TEAMS}
    parks = sorted({g["park"] for g in games})
    pf = {p: 1.0 for p in parks}
    hs_tot = sum(g["hs"] for g in games)
    as_tot = sum(g["as"] for g in games)
    home_edge = (hs_tot / as_tot) ** 0.5

    def mu(g, side):
        if side == "home":
            return lg * off[g["home"]] * dfn[g["away"]] * pf[g["park"]] * home_edge
        return lg * off[g["away"]] * dfn[g["home"]] * pf[g["park"]] / home_edge

    for _ in range(rounds):
        for table, getter in ((off, "off"), (dfn, "def"), (pf, "park")):
            num: dict[str, float] = {}
            den: dict[str, float] = {}
            for g in games:
                for side, scored, conceded in (("home", g["hs"], g["as"]),
                                               ("away", g["as"], g["hs"])):
                    team = g[side]
                    other = g["away"] if side == "home" else g["home"]
                    exp = mu(g, side)
                    if getter == "off":
                        k = team
                        base = exp / off[team]
                        num[k] = num.get(k, 0) + scored
                    elif getter == "def":
                        k = other
                        base = exp / dfn[other]
                        num[k] = num.get(k, 0) + scored
                    else:
                        k = g["park"]
                        base = exp / pf[g["park"]]
                        num[k] = num.get(k, 0) + scored
                    den[k] = den.get(k, 0) + base
            for k in table:
                if den.get(k):
                    table[k] = num[k] / den[k]
        # 正規化: 讓 off 與 park 的加權平均為 1，變異全部留在相對值上
        mo = sum(off.values()) / len(off)
        for t in off:
            off[t] /= mo
        for t in dfn:
            dfn[t] *= mo
        mp = sum(pf[g["park"]] for g in games) / n
        for p in pf:
            pf[p] /= mp
        for t in dfn:
            dfn[t] *= mp

    pred = sum(mu(g, "home") + mu(g, "away") for g in games)
    return {"lg": lg, "off": off, "def": dfn, "pf": pf, "home_edge": home_edge,
            "n": n, "pred": pred,
            "actual": sum(g["hs"] + g["as"] for g in games)}


def shrink_parks(games: list[dict], pf: dict[str, float]) -> tuple[dict, dict]:
    """經驗貝氏收縮。回傳 (收縮後係數, 各球場場次)。"""
    counts: dict[str, int] = {}
    for g in games:
        counts[g["park"]] = counts.get(g["park"], 0) + 1
    primary = [p for p, c in counts.items() if c >= PRIMARY_MIN_GAMES]
    totals = [g["hs"] + g["as"] for g in games]
    mean = sum(totals) / len(totals)
    sd = (sum((x - mean) ** 2 for x in totals) / len(totals)) ** 0.5
    raw = [pf[p] for p in primary]
    m = sum(raw) / len(raw)
    var_obs = sum((x - m) ** 2 for x in raw) / (len(raw) - 1)
    var_noise = sum((sd / mean) ** 2 / counts[p] for p in primary) / len(primary)
    var_true = max(var_obs - var_noise, 1e-6)
    out = {}
    for p in primary:
        noise = (sd / mean) ** 2 / counts[p]
        w = var_true / (var_true + noise)
        out[p] = 1.0 + w * (pf[p] - 1.0)
    return out, counts


def bullpen(games: list[dict], pf_shrunk: dict, lg: float,
            refresh: bool) -> dict[str, float]:
    """各隊救援投手的合計失分率係數（球場曝險調整 + 收縮）。"""
    expo = {t: [] for t in TEAMS}
    for g in games:
        f = pf_shrunk.get(g["park"], 1.0)
        expo[g["home"]].append(f)
        expo[g["away"]].append(f)
    exposure = {t: (sum(v) / len(v) if v else 1.0) for t, v in expo.items()}

    def ip_to_float(x: str) -> float | None:
        m = re.match(r"^(\d+)(?:\.(\d))?$", x)
        return (int(m.group(1)) + (int(m.group(2)) / 3 if m.group(2) else 0.0)
                if m else None)

    out = {}
    for code, team in CODES.items():
        html = fetch(f"https://npb.jp/bis/2026/stats/idp1_{code}.html",
                     f"pit_{code}.html", refresh)
        hdr, rows = None, []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
            c = [re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", x)).replace("&nbsp;", "")
                 for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, flags=re.S)]
            if len(c) < 20:
                continue
            if c[0] == "選手":
                hdr = {n: i for i, n in enumerate(c)}
            else:
                rows.append(c)
        ip_tot = r_tot = 0.0
        for c in rows:
            ip = ip_to_float(c[hdr["投球回"]])
            g_ = int(c[hdr["登板"]])
            if not ip or not g_:
                continue
            if ip / g_ < RELIEF_IP_PER_GAME:
                ip_tot += ip
                r_tot += int(c[hdr["失点"]])
        shrunk = ((r_tot + lg / 9 * SHRINK_IP) * 9 / (ip_tot + SHRINK_IP)
                  / exposure[team])
        out[team] = shrunk / lg
    return out


def block(d: dict, reverse: bool, keep=None) -> str:
    items = sorted(d.items(), key=lambda x: (-x[1] if reverse else x[1]))
    if keep is not None:
        items = [(k, v) for k, v in items if k in keep]
    return "\n".join(f'    "{k}": {v:.4f},' for k, v in items)


def write_config(text: str, var: str, body: str) -> str:
    m = re.compile(rf"(?P<h>^{var} = \{{\n)(?P<b>.*?)(?P<t>^\}}$)",
                   re.S | re.M).search(text)
    if not m:
        raise SystemExit(f"找不到 {var}")
    return text[:m.start("b")] + body + "\n" + text[m.start("t"):]


def _emit(lines: list[str]) -> None:
    """把累積的輸出一次印出; 管線被提早關掉時安靜收工。

    到這裡副作用 (寫檔) 已經完成，所以 BrokenPipeError 只是「沒人在讀」，
    不是失敗。
    """
    try:
        print("\n".join(lines))
        sys.stdout.flush()
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只印出，不寫檔")
    ap.add_argument("--no-refresh", action="store_true",
                    help="使用 /tmp 快取，不重新抓取")
    ap.add_argument("--as-of", default="", help="寫進 AS_OF 的字串")
    ap.add_argument("--through", default="", help="只用此日期(含)以前的比賽，供回歸驗證")
    args = ap.parse_args()

    # ⚠️ 全部先算完、**先寫檔**，最後才印。
    #
    # 2026-09-16 的自動結算是這樣跑的:
    #
    #     python3 scripts/refresh_calibration.py --as-of "..." | head -4 && ...
    #
    # `head` 讀滿 4 行就關掉管線，python 收到 SIGPIPE 在寫檔 **之前** 就死了，
    # 而 `head` 自己回 0，所以 `&&` 一路往下跑、回報還寫著「校準已更新」。
    # 那天的定價與結算其實用的是前一天的係數。
    # 這和同一週 pytest 被 `| tail` 吞掉結束狀態是同一個坑。
    #
    # 防法不是「記得不要接管線」——是把有副作用的那一步排在輸出前面，
    # 這樣就算輸出被截斷，該做的事也已經做完了。
    lines: list[str] = []

    games = parse_games(refresh=not args.no_refresh)
    if args.through:
        games = [g for g in games if g["date"] <= args.through]
    lines.append(f"已打完的例行賽: {len(games)} 場")
    res = fit(games)
    lines.append(f"配適檢核: 預測總得分 {res['pred']:.0f} vs 實際 {res['actual']} "
                 f"({res['pred'] / res['actual']:.4f})")
    lines.append(f"聯盟每隊每場 {res['lg']:.4f}　主場乘數 {res['home_edge']:.4f}")

    pf_shrunk, counts = shrink_parks(games, res["pf"])
    lines.append(f"\n主要球場 ({PRIMARY_MIN_GAMES} 場以上) {len(pf_shrunk)} 座:")
    for p, v in sorted(pf_shrunk.items(), key=lambda x: -x[1]):
        lines.append(f"  {p:<16} {counts[p]:>3} 場  {res['pf'][p]:.3f} -> {v:.4f}")
    minor = {p: c for p, c in counts.items() if c < PRIMARY_MIN_GAMES}
    if minor:
        lines.append("\n場次不足、係數不可用 (下游退回中性值 1.0): "
                     + "、".join(f"{p} {c} 場" for p, c in sorted(minor.items())))

    pen = bullpen(games, pf_shrunk, res["lg"], refresh=not args.no_refresh)
    lines.append("\n牛棚係數:")
    for t, v in sorted(pen.items(), key=lambda x: x[1]):
        lines.append(f"  {t:<10} {v:.4f}")

    if args.dry_run:
        lines.append("\n--dry-run，未寫檔")
        _emit(lines)
        return

    text = CONFIG.read_text()
    text = write_config(text, "PARK_FACTORS_2026", block(pf_shrunk, True))
    text = write_config(text, "TEAM_OFFENCE", block(res["off"], True))
    text = write_config(text, "TEAM_DEFENCE_SEASON", block(res["def"], False))
    text = write_config(text, "BULLPEN_FACTOR", block(pen, False))
    text = re.sub(r"^SAMPLE_GAMES = \d+$", f"SAMPLE_GAMES = {len(games)}",
                  text, flags=re.M)
    dates = sorted(g["date"] for g in games if g["date"])
    if dates:
        text = re.sub(r'^SAMPLE_RANGE = ".*"$',
                      f'SAMPLE_RANGE = "{dates[0]} ~ {dates[-1]}"',
                      text, flags=re.M)
    text = re.sub(r"^LEAGUE_RPG = [\d.]+$", f"LEAGUE_RPG = {res['lg']:.4f}",
                  text, flags=re.M)
    text = re.sub(r"^HOME_EDGE = [\d.]+$", f"HOME_EDGE = {res['home_edge']:.4f}",
                  text, flags=re.M)
    if args.as_of:
        text = re.sub(r'^AS_OF = ".*"$', f'AS_OF = "{args.as_of}"', text, flags=re.M)
    CONFIG.write_text(text)
    lines.append(f"\n已寫回 {CONFIG.relative_to(ROOT)}")
    _emit(lines)


if __name__ == "__main__":
    main()
