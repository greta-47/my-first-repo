"""
Patterns Analyst Agent - Detect early warning signs and risk patterns.

This module implements hybrid deterministic-first, model-second risk analysis:
- Baseline calculation per member (warm-up period + monthly refresh)
- Multi-window analysis (3/14/30-day signals)
- Structured text taxonomy (mood_neg, craving_high, safety_lang_present)
- Reason codes for transparency (sleep_low + isolation_up + neg_affect)

Key principles:
- Deterministic rules first for transparency
- Model adds nuance only where rules can't capture it
- Token/latency budget constraints
- All outputs include confidence scores and reason codes
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional


@dataclass
class CheckInData:
    """Normalized check-in data for analysis."""

    user_id: str
    adherence: int
    mood_trend: int
    cravings: int
    sleep_hours: float
    isolation: int
    ts: str


@dataclass
class Signal:
    """Individual risk signal detected."""

    signal_type: str
    window: Literal["3day", "14day", "30day"]
    value: float
    baseline: Optional[float]
    deviation: Optional[float]
    confidence: float


@dataclass
class PatternsAnalysisResult:
    """Structured output from Patterns Analyst."""

    risk_band: Literal["low", "elevated", "moderate", "high", "insufficient_data"]
    score: Optional[int]
    signals: List[Signal]
    windows: dict[str, dict]  # Window-level aggregates
    reason_codes: List[str]
    confidence: float
    metadata: dict


class PatternsAnalyst:
    """
    Patterns Analyst Agent - Detect early warning signs.

    Uses hybrid approach:
    1. Calculate baselines per member (warm-up: 7 days or 3 check-ins)
    2. Analyze 3/14/30-day windows
    3. Apply deterministic rules with transparent weights
    4. Generate reason codes for clinical transparency
    """

    MIN_CHECKINS_FOR_BASELINE = 3
    BASELINE_WARMUP_DAYS = 7

    SLEEP_LOW_THRESHOLD = 5.0  # hours
    ISOLATION_HIGH_THRESHOLD = 70  # 0-100 scale
    ADHERENCE_LOW_THRESHOLD = 50  # percent
    CRAVINGS_HIGH_THRESHOLD = 60  # 0-100 scale
    MOOD_DECLINE_THRESHOLD = -5  # mood_trend scale

    def __init__(self):
        self.baselines_cache: dict[str, dict] = {}  # In-memory cache for MVP

    def analyze(self, user_id: str, checkin_history: List[CheckInData]) -> PatternsAnalysisResult:
        """
        Analyze check-in history and detect risk patterns.

        Args:
            user_id: User ID for baseline tracking
            checkin_history: List of check-ins (ordered by timestamp)

        Returns:
            PatternsAnalysisResult with risk assessment
        """
        if len(checkin_history) < 3:
            return PatternsAnalysisResult(
                risk_band="insufficient_data",
                score=None,
                signals=[],
                windows={},
                reason_codes=["INSUFFICIENT_DATA"],
                confidence=0.0,
                metadata={
                    "checkins_count": len(checkin_history),
                    "min_required": 3,
                },
            )

        if user_id not in self.baselines_cache:
            self.baselines_cache[user_id] = self._calculate_baselines(checkin_history)

        baselines = self.baselines_cache[user_id]

        windows_data = {
            "3day": self._analyze_window(checkin_history, days=3, baselines=baselines),
            "14day": self._analyze_window(checkin_history, days=14, baselines=baselines),
            "30day": self._analyze_window(checkin_history, days=30, baselines=baselines),
        }

        signals = self._detect_signals(windows_data, baselines)

        reason_codes = self._generate_reason_codes(signals, windows_data)

        score, confidence = self._calculate_risk_score(signals, reason_codes)

        risk_band = self._determine_risk_band(score)

        return PatternsAnalysisResult(
            risk_band=risk_band,
            score=score,
            signals=signals,
            windows=windows_data,
            reason_codes=reason_codes,
            confidence=confidence,
            metadata={
                "checkins_analyzed": len(checkin_history),
                "baselines": baselines,
                "windows_available": list(windows_data.keys()),
            },
        )

    def _calculate_baselines(self, checkin_history: List[CheckInData]) -> dict:
        """Calculate member-specific baselines from historical data."""
        baseline_data = checkin_history[:10] if len(checkin_history) >= 10 else checkin_history

        if len(baseline_data) < self.MIN_CHECKINS_FOR_BASELINE:
            return {
                "sleep_hours": 7.0,
                "isolation": 30.0,
                "adherence": 70.0,
                "cravings": 40.0,
                "mood_trend": 0.0,
                "is_default": True,
            }

        return {
            "sleep_hours": statistics.mean([c.sleep_hours for c in baseline_data]),
            "isolation": statistics.mean([c.isolation for c in baseline_data]),
            "adherence": statistics.mean([c.adherence for c in baseline_data]),
            "cravings": statistics.mean([c.cravings for c in baseline_data]),
            "mood_trend": statistics.mean([c.mood_trend for c in baseline_data]),
            "is_default": False,
        }

    def _analyze_window(
        self, checkin_history: List[CheckInData], days: int, baselines: dict
    ) -> dict:
        """Analyze specific time window (3/14/30 days)."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        window_checkins = [
            c
            for c in checkin_history
            if datetime.fromisoformat(c.ts.replace("Z", "+00:00")) >= cutoff
        ]

        if not window_checkins:
            return {"available": False, "count": 0}

        return {
            "available": True,
            "count": len(window_checkins),
            "sleep_avg": statistics.mean([c.sleep_hours for c in window_checkins]),
            "sleep_min": min([c.sleep_hours for c in window_checkins]),
            "isolation_avg": statistics.mean([c.isolation for c in window_checkins]),
            "isolation_max": max([c.isolation for c in window_checkins]),
            "adherence_avg": statistics.mean([c.adherence for c in window_checkins]),
            "adherence_min": min([c.adherence for c in window_checkins]),
            "cravings_avg": statistics.mean([c.cravings for c in window_checkins]),
            "cravings_max": max([c.cravings for c in window_checkins]),
            "mood_avg": statistics.mean([c.mood_trend for c in window_checkins]),
            "mood_min": min([c.mood_trend for c in window_checkins]),
        }

    def _detect_signals(self, windows_data: dict, baselines: dict) -> List[Signal]:
        """Detect risk signals across all windows using deterministic rules."""
        signals = []

        for window_name, window in windows_data.items():
            if not window.get("available"):
                continue

            if window["sleep_avg"] < self.SLEEP_LOW_THRESHOLD:
                deviation = None
                if not baselines.get("is_default"):
                    deviation = window["sleep_avg"] - baselines["sleep_hours"]

                signals.append(
                    Signal(
                        signal_type="sleep_low",
                        window=window_name,  # type: ignore
                        value=window["sleep_avg"],
                        baseline=baselines["sleep_hours"],
                        deviation=deviation,
                        confidence=0.9 if deviation and deviation < -1.5 else 0.7,
                    )
                )

            if window["isolation_avg"] > self.ISOLATION_HIGH_THRESHOLD:
                deviation = None
                if not baselines.get("is_default"):
                    deviation = window["isolation_avg"] - baselines["isolation"]

                signals.append(
                    Signal(
                        signal_type="isolation_up",
                        window=window_name,  # type: ignore
                        value=window["isolation_avg"],
                        baseline=baselines["isolation"],
                        deviation=deviation,
                        confidence=0.85 if deviation and deviation > 20 else 0.7,
                    )
                )

            if window["adherence_avg"] < self.ADHERENCE_LOW_THRESHOLD:
                deviation = None
                if not baselines.get("is_default"):
                    deviation = window["adherence_avg"] - baselines["adherence"]

                signals.append(
                    Signal(
                        signal_type="adherence_low",
                        window=window_name,  # type: ignore
                        value=window["adherence_avg"],
                        baseline=baselines["adherence"],
                        deviation=deviation,
                        confidence=0.9,  # High confidence - direct measure
                    )
                )

            if window["cravings_avg"] > self.CRAVINGS_HIGH_THRESHOLD:
                deviation = None
                if not baselines.get("is_default"):
                    deviation = window["cravings_avg"] - baselines["cravings"]

                signals.append(
                    Signal(
                        signal_type="cravings_high",
                        window=window_name,  # type: ignore
                        value=window["cravings_avg"],
                        baseline=baselines["cravings"],
                        deviation=deviation,
                        confidence=0.85,
                    )
                )

            if window["mood_avg"] < self.MOOD_DECLINE_THRESHOLD:
                deviation = None
                if not baselines.get("is_default"):
                    deviation = window["mood_avg"] - baselines["mood_trend"]

                signals.append(
                    Signal(
                        signal_type="mood_decline",
                        window=window_name,  # type: ignore
                        value=window["mood_avg"],
                        baseline=baselines["mood_trend"],
                        deviation=deviation,
                        confidence=0.75,  # Mood is subjective
                    )
                )

        return signals

    def _generate_reason_codes(self, signals: List[Signal], windows_data: dict) -> List[str]:
        """Generate transparent reason codes for clinical review."""
        codes = []

        signal_types = defaultdict(list)
        for sig in signals:
            signal_types[sig.signal_type].append(sig)

        if "sleep_low" in signal_types:
            codes.append("SLEEP_DISRUPTION")

        if "isolation_up" in signal_types:
            codes.append("SOCIAL_WITHDRAWAL")

        if "adherence_low" in signal_types:
            codes.append("ADHERENCE_DECLINE")

        if "cravings_high" in signal_types:
            codes.append("CRAVING_SPIKE")

        if "mood_decline" in signal_types:
            codes.append("MOOD_DETERIORATION")

        if "sleep_low" in signal_types and "isolation_up" in signal_types:
            codes.append("SLEEP_ISOLATION_PATTERN")

        if "mood_decline" in signal_types and "adherence_low" in signal_types:
            codes.append("MOOD_ADHERENCE_PATTERN")

        if len(signal_types) >= 3:
            codes.append("MULTIPLE_RISK_FACTORS")

        return codes

    def _calculate_risk_score(
        self, signals: List[Signal], reason_codes: List[str]
    ) -> tuple[int, float]:
        """Calculate composite risk score (0-100) with confidence."""
        if not signals:
            return 0, 1.0

        window_weights = {"3day": 1.5, "14day": 1.0, "30day": 0.7}

        weighted_sum = 0.0
        total_weight = 0.0

        for signal in signals:
            type_scores = {
                "sleep_low": 20,
                "isolation_up": 25,
                "adherence_low": 30,
                "cravings_high": 15,
                "mood_decline": 15,
            }

            base_score = type_scores.get(signal.signal_type, 10)
            window_weight = window_weights.get(signal.window, 1.0)

            weighted_sum += base_score * signal.confidence * window_weight
            total_weight += signal.confidence * window_weight

        score = int(min(100, weighted_sum / total_weight if total_weight > 0 else 0))

        confidence = statistics.mean([s.confidence for s in signals]) if signals else 0.0

        return score, confidence

    def _determine_risk_band(self, score: int) -> Literal["low", "elevated", "moderate", "high"]:
        """Map score to risk band (aligned with existing v0_score bands)."""
        if score < 30:
            return "low"
        elif score < 55:
            return "elevated"
        elif score < 75:
            return "moderate"
        else:
            return "high"
