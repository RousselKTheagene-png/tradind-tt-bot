"""Unit tests for feature extraction and regime classification."""
import numpy as np
import pandas as pd
import pytest

from src.intelligence.features import adx, extract_features, hurst
from src.intelligence.regime import Regime, RegimeClassifier, classify_regime


def _trending(n: int = 400, drift: float = 0.005, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, 0.005, n)
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(rng.normal(0, 0.002, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.002, n)))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": rng.integers(1, 1000, n)}, index=idx)


def _ranging(n: int = 400, seed: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    # Mean-reverting around 100.
    close = 100 + 2 * np.sin(np.linspace(0, 10 * np.pi, n)) + rng.normal(0, 0.3, n)
    high = close + np.abs(rng.normal(0, 0.2, n))
    low = close - np.abs(rng.normal(0, 0.2, n))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": rng.integers(1, 1000, n)}, index=idx)


def _high_vol(n: int = 400, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, 0.05, n)  # ~5% vol per bar -> huge ATR
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(rng.normal(0, 0.03, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.03, n)))
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": rng.integers(1, 1000, n)}, index=idx)


def test_adx_returns_valid_range():
    df = _trending()
    a = adx(df).dropna()
    assert (a >= 0).all() and (a <= 100).all()


def test_adx_higher_for_trending_than_ranging():
    adx_trend = adx(_trending()).iloc[-1]
    adx_range = adx(_ranging()).iloc[-1]
    assert adx_trend > adx_range


def test_hurst_bounded_for_random_walk():
    rng = np.random.default_rng(0)
    series = pd.Series(np.cumsum(rng.normal(0, 1, 500)))
    h = hurst(series)
    assert 0.0 < h < 1.5  # empirical estimator — loose bounds


def test_extract_features_has_expected_columns():
    feats = extract_features(_trending())
    assert set(feats.columns) == {"adx", "atr_pct", "ret_mean", "ret_std", "hurst"}
    assert len(feats) == 400


def test_rule_classifier_identifies_trend():
    r = classify_regime(_trending(drift=0.01))
    assert r in (Regime.TRENDING_UP, Regime.HIGH_VOLATILITY)


def test_rule_classifier_identifies_ranging():
    r = classify_regime(_ranging())
    assert r in (Regime.RANGING, Regime.UNKNOWN)


def test_rule_classifier_identifies_high_vol():
    r = classify_regime(_high_vol())
    assert r == Regime.HIGH_VOLATILITY


def test_kmeans_classifier_fits_and_predicts():
    pytest.importorskip("sklearn")
    clf = RegimeClassifier(method="kmeans", n_clusters=3)
    clf.fit(_trending())
    r = clf.classify(_trending())
    assert isinstance(r, Regime)


def test_kmeans_classifier_raises_before_fit():
    pytest.importorskip("sklearn")
    clf = RegimeClassifier(method="kmeans")
    with pytest.raises(RuntimeError):
        clf.classify(_trending())


def test_invalid_method_rejected():
    with pytest.raises(ValueError):
        RegimeClassifier(method="does_not_exist")
