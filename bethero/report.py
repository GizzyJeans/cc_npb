"""輸出使用者指定格式的下注報告 (繁體中文)。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from .bankroll import Bankroll
from .board import BoardGame
from .ev import BetEvaluation
from .gates import DataReadiness, Grade, GradedBet
from .model import GameDistributions


@dataclass
class GameAnalysis:
    """一場比賽的完整分析結果。"""

    game: BoardGame
    readiness: DataReadiness
    selection: str = ""
    """投注選項描述，例如「主隊 -0.5」或「大分 7.25」。"""

    line_label: str = ""
    evaluation: Optional[BetEvaluation] = None
    graded: Optional[GradedBet] = None
    dists: Optional[GameDistributions] = None

    pitching_note: str = ""
    lineup_note: str = ""
    bullpen_note: str = ""
    park_weather_note: str = ""
    market_note: str = ""
    rationale: str = ""
    cancel_conditions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    @property
    def grade(self) -> Grade:
        return self.graded.grade if self.graded else Grade.NO_BET

    @property
    def stake(self) -> float:
        if self.evaluation and self.grade is Grade.RECOMMEND:
            return self.evaluation.stake
        return 0.0


@dataclass
class DailyReport:
    """單日報告。"""

    date: str
    bankroll: Bankroll
    analyses: list[GameAnalysis]
    data_as_of: str = ""
    sources: list[str] = field(default_factory=list)
    global_notes: list[str] = field(default_factory=list)

    # -- 區塊 ---------------------------------------------------------------

    def slate_table(self) -> str:
        header = (
            "| 優先 | 比賽 | 投注選項 | 盤口與賠率 | 模型機率 | 公平賠率 "
            "| EV | 建議注碼 | 最低接受賠率 | 狀態 |\n"
            "|---|---|---|---|---|---|---|---|---|---|"
        )
        rows: list[str] = []
        ranked = sorted(
            self.analyses,
            key=lambda a: (
                a.grade is not Grade.RECOMMEND,
                -(a.evaluation.ev if a.evaluation else -1),
            ),
        )
        for i, a in enumerate(ranked, 1):
            ev = a.evaluation
            if ev is None:
                rows.append(
                    f"| {i} | {a.game.matchup} | — | {a.line_label or '—'} "
                    f"| — | — | — | 0 | — | **{a.grade.value}** |"
                )
                continue
            rows.append(
                f"| {i} | {a.game.matchup} | {a.selection} | {a.line_label} "
                f"| {ev.model_prob:.1%} | {ev.fair_hk:.3f} | {ev.ev:+.1%} "
                f"| {a.stake:,.0f} | {ev.min_hk:.3f} | **{a.grade.value}** |"
            )
        return header + "\n" + "\n".join(rows)

    def per_game_sections(self) -> str:
        blocks: list[str] = []
        for a in self.analyses:
            lines = [
                f"### {a.game.matchup}　{a.game.start_time}　{a.game.venue}",
                "",
                f"- **投手對位**：{a.pitching_note or '資料不足'}",
                f"- **打線**：{a.lineup_note or '資料不足'}",
                f"- **牛棚**：{a.bullpen_note or '資料不足'}",
                f"- **球場與天氣**：{a.park_weather_note or '資料不足'}",
                f"- **市場盤口變化**：{a.market_note or '資料不足'}",
                f"- **結論**：{a.rationale or '—'}",
            ]
            if a.risks:
                lines.append("- **主要風險**：" + "；".join(a.risks))
            if a.cancel_conditions:
                lines.append("- **取消投注條件**：" + "；".join(a.cancel_conditions))
            audit = a.game.audit()
            if audit:
                lines.append("- **盤口待確認**：" + "；".join(audit))
            waived = a.readiness.waived_reasons()
            if waived:
                lines.append("- **已放棄的門檻**：" + "；".join(waived))
            gaps = a.readiness.blocking_reasons() + a.readiness.soft_gaps()
            if gaps:
                lines.append("- **資料缺口**：" + "；".join(gaps))
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def summary(self) -> str:
        total = sum(a.stake for a in self.analyses)
        pct = total / self.bankroll.total if self.bankroll.total else 0.0
        recommended = [a for a in self.analyses if a.grade is Grade.RECOMMEND]
        observe = [a for a in self.analyses if a.grade is Grade.OBSERVE]
        no_bet = [a for a in self.analyses if a.grade is Grade.NO_BET]

        max_loss = sum(a.stake for a in recommended)

        lines = [
            f"- **當日總下注金額**：{total:,.0f} 單位",
            f"- **占本金比例**：{pct:.2%}（本金 {self.bankroll.total:,.0f} 單位）",
            f"- **最大可能虧損**：{max_loss:,.0f} 單位"
            + ("（無部位，虧損為 0）" if max_loss == 0 else ""),
        ]
        if observe:
            lines.append(
                "- **尚待確認的比賽**：\n"
                + "\n".join(
                    f"  - {a.game.matchup} — " + "；".join(a.graded.reasons[:3])
                    for a in observe
                    if a.graded
                )
            )
        else:
            lines.append("- **尚待確認的比賽**：無")
        if no_bet:
            lines.append(
                "- **明確不建議下注的比賽**：\n"
                + "\n".join(
                    f"  - {a.game.matchup} — "
                    + "；".join((a.graded.reasons if a.graded else ["資料不足"])[:3])
                    for a in no_bet
                )
            )
        return "\n".join(lines)

    def render(self) -> str:
        parts = [
            f"# NPB 量化投注報告　{self.date}",
            "",
            f"資料最後更新時間：{self.data_as_of or datetime.utcnow().isoformat()}",
            "",
        ]
        if self.global_notes:
            parts += ["## 全日提醒", ""] + [f"- {n}" for n in self.global_notes] + [""]
        parts += [
            "## 下注單（依優先度排序）",
            "",
            self.slate_table(),
            "",
            "## 逐場說明",
            "",
            self.per_game_sections(),
            "",
            "## 當日總結",
            "",
            self.summary(),
        ]
        if self.sources:
            parts += ["", "## 資料來源", ""] + [f"- {s}" for s in self.sources]
        return "\n".join(parts)


__all__ = ["GameAnalysis", "DailyReport"]
