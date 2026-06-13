"""
step2_ml.py — Lightweight ML Prediction Module
Uses: Moving Average + Exponential Smoothing (no heavy frameworks)
Predicts crowd count 5–15 minutes ahead per zone.
"""

from typing import List, Dict, Optional, Tuple
from collections import deque
import math


# ─────────────────────────────────────────────
# Simple Moving Average Forecaster
# ─────────────────────────────────────────────
class MovingAverageForecaster:
    """
    Computes a simple / weighted moving average over the last N ticks.
    Used for short-horizon (1–5 step) smoothing.
    """

    def __init__(self, window: int = 5):
        self.window = window
        self._buffers: Dict[str, deque] = {}

    def update(self, zone_id: str, value: float):
        if zone_id not in self._buffers:
            self._buffers[zone_id] = deque(maxlen=self.window)
        self._buffers[zone_id].append(value)

    def predict(self, zone_id: str, steps_ahead: int = 1) -> Optional[float]:
        buf = self._buffers.get(zone_id)
        if not buf or len(buf) < 2:
            return None
        avg = sum(buf) / len(buf)
        # linear trend from first half → second half
        half = max(1, len(buf) // 2)
        trend = (sum(list(buf)[half:]) / half) - (sum(list(buf)[:half]) / half)
        return max(0.0, avg + trend * steps_ahead)


# ─────────────────────────────────────────────
# Exponential Smoothing Forecaster  (Holt's method)
# ─────────────────────────────────────────────
class ExponentialSmoothingForecaster:
    """
    Double exponential smoothing (Holt's linear trend method).
    α controls level smoothing, β controls trend smoothing.
    Forecasts h steps ahead: F(t+h) = level + h * trend
    """

    def __init__(self, alpha: float = 0.3, beta: float = 0.2):
        assert 0 < alpha < 1 and 0 < beta < 1
        self.alpha = alpha
        self.beta  = beta
        self._state: Dict[str, Dict] = {}   # {zone_id: {level, trend}}

    def update(self, zone_id: str, value: float):
        if zone_id not in self._state:
            self._state[zone_id] = {"level": value, "trend": 0.0, "prev_level": value}
            return

        s = self._state[zone_id]
        prev_level = s["level"]
        prev_trend = s["trend"]

        new_level = self.alpha * value + (1 - self.alpha) * (prev_level + prev_trend)
        new_trend = self.beta * (new_level - prev_level) + (1 - self.beta) * prev_trend

        s["level"]      = new_level
        s["trend"]      = new_trend
        s["prev_level"] = prev_level

    def predict(self, zone_id: str, steps_ahead: int = 5) -> Optional[float]:
        s = self._state.get(zone_id)
        if s is None:
            return None
        forecast = s["level"] + steps_ahead * s["trend"]
        return max(0.0, forecast)

    def trend_direction(self, zone_id: str) -> str:
        s = self._state.get(zone_id)
        if s is None:
            return "unknown"
        t = s["trend"]
        if t > 2:   return "rapidly increasing ▲▲"
        if t > 0.5: return "increasing ▲"
        if t < -2:  return "rapidly decreasing ▼▼"
        if t < -0.5:return "decreasing ▼"
        return "stable ─"


# ─────────────────────────────────────────────
# Unified Crowd Predictor
# ─────────────────────────────────────────────
class CrowdPredictor:
    """
    Combines MovingAverage + ExponentialSmoothing.
    Exposes a single .predict() interface per zone.
    Tick resolution = 1 minute (configurable).
    """

    def __init__(
        self,
        tick_seconds: int = 60,
        ma_window: int = 6,
        es_alpha: float = 0.35,
        es_beta: float = 0.20,
    ):
        self.tick_seconds = tick_seconds          # real-world seconds per tick
        self.ma  = MovingAverageForecaster(window=ma_window)
        self.es  = ExponentialSmoothingForecaster(alpha=es_alpha, beta=es_beta)
        self._raw_history: Dict[str, List[float]] = {}

    def feed(self, zone_id: str, people_count: float):
        """Call once per tick per zone with current count."""
        self.ma.update(zone_id, people_count)
        self.es.update(zone_id, people_count)
        self._raw_history.setdefault(zone_id, []).append(people_count)

    def predict_at_minutes(
        self, zone_id: str, minutes_ahead: int = 5
    ) -> Dict:
        """
        Returns prediction dict for the given zone at +N minutes.
        Blends MA and ES 50/50 for robustness.
        """
        ticks_ahead = max(1, round((minutes_ahead * 60) / self.tick_seconds))

        ma_pred = self.ma.predict(zone_id, ticks_ahead)
        es_pred = self.es.predict(zone_id, ticks_ahead)

        if ma_pred is None and es_pred is None:
            return {"zone_id": zone_id, "minutes_ahead": minutes_ahead, "predicted_count": None, "confidence": "low"}

        preds = [p for p in [ma_pred, es_pred] if p is not None]
        blended = sum(preds) / len(preds)

        history = self._raw_history.get(zone_id, [])
        confidence = "high" if len(history) >= 10 else ("medium" if len(history) >= 5 else "low")

        return {
            "zone_id":         zone_id,
            "minutes_ahead":   minutes_ahead,
            "predicted_count": round(blended),
            "ma_prediction":   round(ma_pred)  if ma_pred  is not None else None,
            "es_prediction":   round(es_pred)  if es_pred  is not None else None,
            "trend":           self.es.trend_direction(zone_id),
            "confidence":      confidence,
        }

    def predict_range(
        self, zone_id: str, horizons: Tuple[int, ...] = (5, 10, 15)
    ) -> List[Dict]:
        return [self.predict_at_minutes(zone_id, m) for m in horizons]

    def summarise_zone(self, zone_id: str, area_sqm: float) -> str:
        p5  = self.predict_at_minutes(zone_id, 5)
        p15 = self.predict_at_minutes(zone_id, 15)
        trend = self.es.trend_direction(zone_id)

        def density(count):
            return round(count / area_sqm, 2) if area_sqm > 0 and count else 0.0

        lines = [
            f"  Forecast [{zone_id}]  Trend: {trend}",
            f"    +5 min  → {p5['predicted_count']} people  ({density(p5['predicted_count'])}/m²)  [{p5['confidence']} confidence]",
            f"    +15 min → {p15['predicted_count']} people  ({density(p15['predicted_count'])}/m²)  [{p15['confidence']} confidence]",
        ]
        return "\n".join(lines)
