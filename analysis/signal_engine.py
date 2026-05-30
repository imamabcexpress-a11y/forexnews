"""
analysis/signal_engine.py - Signal generation with scoring system
"""
from dataclasses import dataclass, field
from typing import Optional, Dict
from loguru import logger

from analysis.technical import analyze_timeframe, extract_key_levels


# ─────────────────────────────────────────
# DATA CLASSES
# ─────────────────────────────────────────
@dataclass
class ScoreBreakdown:
    trend: int = 0       # max 20
    sr: int = 0          # max 20
    rsi: int = 0         # max 10
    volume: int = 0      # max 10
    vwap: int = 0        # max 10
    structure: int = 0   # max 15
    orderblock: int = 0  # max 15

    @property
    def total(self) -> int:
        return self.trend + self.sr + self.rsi + self.volume + self.vwap + self.structure + self.orderblock


@dataclass
class SignalResult:
    symbol: str
    direction: str  # BUY / SELL / NO_TRADE
    strength: str   # STRONG / NORMAL / WEAK / NO_TRADE
    entry: Optional[float] = None
    sl: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    tp3: Optional[float] = None
    risk_reward: Optional[float] = None
    score: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    trend_d1: str = "UNKNOWN"
    trend_h4: str = "UNKNOWN"
    trend_h1: str = "UNKNOWN"
    trend_m15: str = "UNKNOWN"
    news_safe: bool = True
    reason: str = ""

    @property
    def confidence(self) -> int:
        return self.score.total

    def signal_label(self) -> str:
        if self.direction == "NO_TRADE":
            return "NO TRADE"
        if self.confidence >= 90:
            return f"STRONG {self.direction}"
        elif self.confidence >= 80:
            return self.direction
        elif self.confidence >= 70:
            return f"WEAK {self.direction}"
        return "NO TRADE"


# ─────────────────────────────────────────
# SCORING LOGIC
# ─────────────────────────────────────────
class SignalScorer:

    def score_trend(self, analyses: dict, direction: str) -> int:
        """Score based on multi-timeframe trend alignment (max 20)"""
        required_tfs = ["D1", "H4", "H1", "M15"]
        aligned = 0
        for tf in required_tfs:
            a = analyses.get(tf)
            if a and a.get("trend") == direction:
                aligned += 1
        return int((aligned / len(required_tfs)) * 20)

    def score_sr(self, current_price: float, levels: dict, direction: str, atr: float) -> int:
        """Score based on proximity to key support/resistance (max 20)"""
        if not levels or atr <= 0:
            return 0

        zone = atr * 0.5
        score = 0

        if direction == "BUY":
            supports = ["S1", "S2", "swing_low", "daily_low", "prev_day_low", "monthly_low"]
            for key in supports:
                lvl = levels.get(key)
                if lvl and abs(current_price - lvl) < zone:
                    score += 5
                    break
        else:
            resistances = ["R1", "R2", "swing_high", "daily_high", "prev_day_high", "monthly_high"]
            for key in resistances:
                lvl = levels.get(key)
                if lvl and abs(current_price - lvl) < zone:
                    score += 5
                    break

        # Double score if at weekly/monthly
        premium_levels = {
            "BUY": ["weekly_low", "monthly_low"],
            "SELL": ["weekly_high", "monthly_high"],
        }
        for key in premium_levels.get(direction, []):
            lvl = levels.get(key)
            if lvl and abs(current_price - lvl) < zone:
                score = min(score + 15, 20)
                break

        return min(score, 20)

    def score_rsi(self, rsi_m15: float, direction: str) -> int:
        """RSI confirmation score (max 10)"""
        if direction == "BUY":
            if rsi_m15 < 35:
                return 10
            elif rsi_m15 < 45:
                return 7
            elif rsi_m15 < 55:
                return 4
        elif direction == "SELL":
            if rsi_m15 > 65:
                return 10
            elif rsi_m15 > 55:
                return 7
            elif rsi_m15 > 45:
                return 4
        return 0

    def score_volume(self, analysis_m15: dict) -> int:
        """Volume confirmation (max 10)"""
        if analysis_m15 and analysis_m15.get("volume_spike"):
            return 10
        return 3

    def score_vwap(self, price: float, vwap: float, direction: str) -> int:
        """VWAP position score (max 10)"""
        if not vwap or vwap == 0:
            return 5
        if direction == "BUY" and price > vwap:
            return 10
        elif direction == "SELL" and price < vwap:
            return 10
        return 2

    def score_structure(self, analyses: dict, direction: str) -> int:
        """Market structure confirmation (max 15)"""
        score = 0
        for tf in ["H1", "M15"]:
            a = analyses.get(tf)
            if not a:
                continue
            struct = a.get("structure", {})
            s_type = struct.get("structure", "UNKNOWN")
            if (direction == "BUY" and s_type == "BULLISH") or (direction == "SELL" and s_type == "BEARISH"):
                score += 7
            if struct.get("bos"):
                score += 1
        return min(score, 15)

    def score_orderblock(self, analyses: dict, price: float, direction: str, atr: float) -> int:
        """Order block proximity score (max 15)"""
        if atr <= 0:
            return 0
        zone = atr * 1.0
        for tf in ["M15", "H1"]:
            a = analyses.get(tf)
            if not a:
                continue
            for ob in a.get("order_blocks", []):
                ob_type = ob.get("type", "")
                if direction == "BUY" and ob_type == "BULLISH_OB":
                    if ob["bottom"] - zone <= price <= ob["top"] + zone:
                        return 15
                elif direction == "SELL" and ob_type == "BEARISH_OB":
                    if ob["bottom"] - zone <= price <= ob["top"] + zone:
                        return 15
        return 0


# ─────────────────────────────────────────
# MAIN SIGNAL ENGINE
# ─────────────────────────────────────────
class SignalEngine:

    def __init__(self):
        self.scorer = SignalScorer()

    def _determine_direction(self, analyses: dict) -> Optional[str]:
        """Multi-TF trend alignment filter"""
        key_tfs = ["D1", "H4", "H1", "M15"]
        trends = [analyses.get(tf, {}).get("trend", "UNKNOWN") for tf in key_tfs]

        bullish = all(t == "BULLISH" for t in trends)
        bearish = all(t == "BEARISH" for t in trends)

        if bullish:
            return "BUY"
        elif bearish:
            return "SELL"
        return None  # Misaligned → NO TRADE

    def _calc_entry_levels(
        self, direction: str, price: float, atr: float, levels: dict
    ) -> dict:
        sl_mult = 1.5
        tp1_mult = 1.5
        tp2_mult = 2.5
        tp3_mult = 4.0

        if direction == "BUY":
            sl = round(price - atr * sl_mult, 5)
            tp1 = round(price + atr * tp1_mult, 5)
            tp2 = round(price + atr * tp2_mult, 5)
            tp3 = round(price + atr * tp3_mult, 5)
        else:
            sl = round(price + atr * sl_mult, 5)
            tp1 = round(price - atr * tp1_mult, 5)
            tp2 = round(price - atr * tp2_mult, 5)
            tp3 = round(price - atr * tp3_mult, 5)

        risk = abs(price - sl)
        reward = abs(tp2 - price)
        rr = round(reward / risk, 2) if risk > 0 else 0

        return {"sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3, "rr": rr}

    def generate(
        self,
        symbol: str,
        mtf_data: dict,
        current_price: float,
        news_safe: bool = True,
    ) -> SignalResult:
        """Generate signal with scoring from multi-timeframe data"""

        # Run analysis for each timeframe
        analyses = {}
        for tf, df in mtf_data.items():
            if df is not None and len(df) >= 30:
                try:
                    analyses[tf] = analyze_timeframe(df, tf)
                except Exception as e:
                    logger.warning(f"Analysis failed {symbol}/{tf}: {e}")

        # Get key levels
        levels = extract_key_levels(
            mtf_data.get("D1"),
            mtf_data.get("H4"),
        )

        # Get ATR from H1
        atr_h1 = analyses.get("H1", {}).get("atr", 0) or 1.0
        rsi_m15 = analyses.get("M15", {}).get("rsi", 50) or 50
        vwap_h1 = analyses.get("H1", {}).get("vwap", current_price) or current_price

        trend_map = {tf: analyses.get(tf, {}).get("trend", "UNKNOWN") for tf in ["D1", "H4", "H1", "M15"]}

        # Determine direction
        direction = self._determine_direction(analyses)

        if direction is None or not news_safe:
            reason = "No trend alignment" if direction is None else "High impact news — no trade"
            return SignalResult(
                symbol=symbol,
                direction="NO_TRADE",
                strength="NO_TRADE",
                trend_d1=trend_map["D1"],
                trend_h4=trend_map["H4"],
                trend_h1=trend_map["H1"],
                trend_m15=trend_map["M15"],
                news_safe=news_safe,
                reason=reason,
            )

        # Score
        score = ScoreBreakdown(
            trend=self.scorer.score_trend(analyses, direction),
            sr=self.scorer.score_sr(current_price, levels, direction, atr_h1),
            rsi=self.scorer.score_rsi(rsi_m15, direction),
            volume=self.scorer.score_volume(analyses.get("M15", {})),
            vwap=self.scorer.score_vwap(current_price, vwap_h1, direction),
            structure=self.scorer.score_structure(analyses, direction),
            orderblock=self.scorer.score_orderblock(analyses, current_price, direction, atr_h1),
        )

        confidence = score.total

        # Reject weak signals
        if confidence < 70:
            return SignalResult(
                symbol=symbol,
                direction="NO_TRADE",
                strength="NO_TRADE",
                score=score,
                trend_d1=trend_map["D1"],
                trend_h4=trend_map["H4"],
                trend_h1=trend_map["H1"],
                trend_m15=trend_map["M15"],
                news_safe=news_safe,
                reason=f"Score too low: {confidence}/100",
            )

        # Calculate entry levels
        entry_levels = self._calc_entry_levels(direction, current_price, atr_h1, levels)

        strength = "STRONG" if confidence >= 90 else "NORMAL" if confidence >= 80 else "WEAK"

        return SignalResult(
            symbol=symbol,
            direction=direction,
            strength=strength,
            entry=round(current_price, 5),
            sl=entry_levels["sl"],
            tp1=entry_levels["tp1"],
            tp2=entry_levels["tp2"],
            tp3=entry_levels["tp3"],
            risk_reward=entry_levels["rr"],
            score=score,
            trend_d1=trend_map["D1"],
            trend_h4=trend_map["H4"],
            trend_h1=trend_map["H1"],
            trend_m15=trend_map["M15"],
            news_safe=news_safe,
            reason=f"Score: {confidence}/100",
        )
