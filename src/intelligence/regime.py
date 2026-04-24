"""Market-regime classification.

Supports two methods:
  - "rules"  : deterministic thresholds on ADX + return_mean + ATR percentile
  - "kmeans" : sklearn KMeans clustering, trained via `fit` on historical data

Strategies can consult `classify(ohlcv)` to filter signals by regime
(e.g. skip trend-following strategies when the market is RANGING).
"""
from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd

from .features import extract_features


class Regime(str, Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_volatility"
    UNKNOWN = "unknown"


# --- Rule-based classifier ---------------------------------------------------

def _rule_classify_row(adx_val: float, ret_mean: float, atr_pct: float,
                       atr_high_thr: float, adx_thr: float = 25.0) -> Regime:
    if np.isnan(adx_val) or np.isnan(ret_mean) or np.isnan(atr_pct):
        return Regime.UNKNOWN
    if atr_pct >= atr_high_thr:
        return Regime.HIGH_VOLATILITY
    if adx_val >= adx_thr:
        return Regime.TRENDING_UP if ret_mean > 0 else Regime.TRENDING_DOWN
    return Regime.RANGING


class RegimeClassifier:
    """Classify the *current* regime from an OHLCV DataFrame."""

    def __init__(
        self,
        method: str = "rules",
        adx_threshold: float = 25.0,
        atr_high_absolute: float = 0.025,
        atr_high_percentile: float = 0.85,
        n_clusters: int = 4,
    ):
        if method not in {"rules", "kmeans"}:
            raise ValueError("method must be 'rules' or 'kmeans'")
        self.method = method
        self.adx_threshold = adx_threshold
        self.atr_high_absolute = atr_high_absolute
        self.atr_high_percentile = atr_high_percentile
        self.n_clusters = n_clusters
        self._model = None
        self._cluster_map: dict[int, Regime] = {}
        self._atr_high_thr: float | None = None

    # --- rules ---------------------------------------------------------------
    def _atr_threshold(self, feats: pd.DataFrame) -> float:
        """Lower of an absolute cut-off and the in-sample high percentile."""
        pctile = float(feats["atr_pct"].quantile(self.atr_high_percentile))
        return min(pctile, self.atr_high_absolute) if pctile > 0 else self.atr_high_absolute

    def _classify_rules(self, feats: pd.DataFrame) -> Regime:
        thr = self._atr_high_thr or self._atr_threshold(feats)
        row = feats.iloc[-1]
        return _rule_classify_row(row["adx"], row["ret_mean"], row["atr_pct"],
                                  atr_high_thr=thr, adx_thr=self.adx_threshold)

    # --- kmeans --------------------------------------------------------------
    def fit(self, ohlcv: pd.DataFrame) -> "RegimeClassifier":
        """Train the KMeans classifier on historical data."""
        from sklearn.cluster import KMeans

        feats = extract_features(ohlcv).dropna()
        if feats.empty:
            raise ValueError("no valid rows after feature extraction")
        self._atr_high_thr = self._atr_threshold(feats)

        X = feats[["adx", "atr_pct", "ret_mean", "ret_std", "hurst"]].values
        km = KMeans(n_clusters=self.n_clusters, n_init=10, random_state=42)
        labels = km.fit_predict(X)
        self._model = km

        # Map each cluster to a Regime by looking at its centroid.
        for cluster_id, centroid in enumerate(km.cluster_centers_):
            adx_c, atr_c, ret_c, _std_c, _hurst_c = centroid
            self._cluster_map[cluster_id] = _rule_classify_row(
                adx_c, ret_c, atr_c, atr_high_thr=self._atr_high_thr,
                adx_thr=self.adx_threshold,
            )
        return self

    def _classify_kmeans(self, feats: pd.DataFrame) -> Regime:
        if self._model is None:
            raise RuntimeError("KMeans classifier not fitted — call .fit() first")
        row = feats.iloc[[-1]][["adx", "atr_pct", "ret_mean", "ret_std", "hurst"]]
        if row.isna().any(axis=None):
            return Regime.UNKNOWN
        label = int(self._model.predict(row.values)[0])
        return self._cluster_map.get(label, Regime.UNKNOWN)

    # --- public API ---------------------------------------------------------
    def classify(self, ohlcv: pd.DataFrame) -> Regime:
        feats = extract_features(ohlcv)
        if self.method == "kmeans":
            return self._classify_kmeans(feats)
        return self._classify_rules(feats)


# Convenience function for ad-hoc use from strategies.
def classify_regime(ohlcv: pd.DataFrame, adx_threshold: float = 25.0) -> Regime:
    return RegimeClassifier(method="rules", adx_threshold=adx_threshold).classify(ohlcv)
