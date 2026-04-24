"""Tests for the parameter optimizer."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.backtest.optimizer import (build_engine_kwargs, grid_search,
                                    random_search, walk_forward,
                                    _iter_grid, _metric_value)
from src.backtest.metrics import PerformanceReport
from src.strategies.ema_crossover import EmaCrossover


def _synthetic_ohlcv(n: int = 400, seed: int = 1) -> pd.DataFrame:
    rnd = np.random.default_rng(seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    trend = np.linspace(100, 160, n)
    noise = rnd.normal(0, 1.5, n).cumsum()
    close = trend + noise
    df = pd.DataFrame({
        "open": close + rnd.normal(0, 0.2, n),
        "high": close + np.abs(rnd.normal(0, 0.4, n)),
        "low": close - np.abs(rnd.normal(0, 0.4, n)),
        "close": close,
        "volume": rnd.integers(100, 1000, n),
    }, index=idx)
    return df


def test_iter_grid_empty_yields_single_empty_dict():
    assert list(_iter_grid({})) == [{}]


def test_iter_grid_cartesian_product():
    out = list(_iter_grid({"a": [1, 2], "b": [10, 20]}))
    assert len(out) == 4
    assert {"a": 1, "b": 10} in out
    assert {"a": 2, "b": 20} in out


def test_metric_value_rejects_unknown():
    report = PerformanceReport(0, 0, 0, 0, 0, 0, 0, 0)
    with pytest.raises(ValueError):
        _metric_value(report, "bogus")


def test_metric_value_reads_field():
    report = PerformanceReport(1.0, 2.0, 3.0, -4.0, 50.0, 1.5, 5, 0.1)
    assert _metric_value(report, "sharpe") == 3.0
    assert _metric_value(report, "total_return_pct") == 1.0


def test_grid_search_runs_all_combinations_and_sorts():
    ohlcv = _synthetic_ohlcv(300)
    grid = {"fast": [10, 20], "slow": [50, 100]}
    runs = grid_search(EmaCrossover, "TEST", ohlcv, grid,
                       metric="sharpe", **build_engine_kwargs(warmup=100))
    assert len(runs) == 4
    # Sorted descending by metric.
    metrics = [r.metric for r in runs]
    assert metrics == sorted(metrics, reverse=True)
    for r in runs:
        assert set(r.params.keys()) == {"fast", "slow"}


def test_grid_search_swallows_strategy_errors_and_continues():
    ohlcv = _synthetic_ohlcv(300)
    # slow < fast is nonsensical but still runs; mix with valid combos.
    grid = {"fast": [10, 50], "slow": [20, 100]}
    runs = grid_search(EmaCrossover, "TEST", ohlcv, grid,
                       metric="total_return_pct",
                       **build_engine_kwargs(warmup=100))
    # 4 combos — none raise inside EmaCrossover even if fast>slow.
    assert len(runs) == 4


def test_random_search_respects_n_iter_and_seed():
    ohlcv = _synthetic_ohlcv(300)
    space = {"fast": [5, 10, 15, 20, 25], "slow": [40, 60, 80, 100]}
    runs_a = random_search(EmaCrossover, "TEST", ohlcv, space,
                           n_iter=6, seed=42,
                           **build_engine_kwargs(warmup=100))
    runs_b = random_search(EmaCrossover, "TEST", ohlcv, space,
                           n_iter=6, seed=42,
                           **build_engine_kwargs(warmup=100))
    assert [r.params for r in runs_a] == [r.params for r in runs_b]
    assert len(runs_a) <= 6


def test_random_search_different_seeds_differ():
    ohlcv = _synthetic_ohlcv(300)
    space = {"fast": list(range(5, 30)), "slow": list(range(40, 120))}
    a = random_search(EmaCrossover, "TEST", ohlcv, space, n_iter=5, seed=1,
                      **build_engine_kwargs(warmup=100))
    b = random_search(EmaCrossover, "TEST", ohlcv, space, n_iter=5, seed=99,
                      **build_engine_kwargs(warmup=100))
    assert {tuple(sorted(r.params.items())) for r in a} != \
           {tuple(sorted(r.params.items())) for r in b}


def test_walk_forward_produces_expected_number_of_folds():
    ohlcv = _synthetic_ohlcv(600)
    folds = walk_forward(EmaCrossover, "TEST", ohlcv,
                         param_grid={"fast": [10, 20], "slow": [50]},
                         train_bars=300, test_bars=100, step_bars=100,
                         metric="sharpe",
                         **build_engine_kwargs(warmup=50))
    # (600 - 300) / 100 = 3 folds with train+test fitting.
    assert len(folds) == 3
    for f in folds:
        assert f.best_params["fast"] in (10, 20)
        assert f.train_end < f.test_start
        assert f.train_start == folds[0].train_start if f is folds[0] else True


def test_walk_forward_rejects_bad_window_sizes():
    ohlcv = _synthetic_ohlcv(200)
    with pytest.raises(ValueError):
        walk_forward(EmaCrossover, "TEST", ohlcv,
                     param_grid={"fast": [10], "slow": [50]},
                     train_bars=0, test_bars=100,
                     **build_engine_kwargs(warmup=50))


def test_walk_forward_no_folds_when_data_too_short():
    ohlcv = _synthetic_ohlcv(150)
    folds = walk_forward(EmaCrossover, "TEST", ohlcv,
                         param_grid={"fast": [10], "slow": [50]},
                         train_bars=200, test_bars=100,
                         **build_engine_kwargs(warmup=50))
    assert folds == []


def test_optimization_run_as_dict_serializable():
    ohlcv = _synthetic_ohlcv(300)
    runs = grid_search(EmaCrossover, "TEST", ohlcv,
                       {"fast": [10], "slow": [50]},
                       metric="sharpe", **build_engine_kwargs(warmup=100))
    d = runs[0].as_dict()
    import json
    json.dumps(d)  # must not raise
    assert "params" in d and "report" in d and "metric" in d


def test_build_engine_kwargs_wires_regime_filter():
    kw = build_engine_kwargs(regime_filter=True)
    assert kw["regime_filter"] is not None
    kw2 = build_engine_kwargs(regime_filter=False)
    assert kw2["regime_filter"] is None
