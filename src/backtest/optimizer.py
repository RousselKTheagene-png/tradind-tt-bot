"""Strategy parameter optimization.

Provides grid search, random search, and walk-forward cross-validation on top
of :class:`BacktestEngine`. Each run honours the same cost model + optional
regime filter used in production so results are comparable to live paper.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field
from typing import Any, Iterable

import pandas as pd

from ..execution.cost_model import CostModel
from ..intelligence.regime import RegimeClassifier
from ..risk.risk_manager import RiskLimits
from ..strategies.base import Strategy
from .engine import BacktestEngine
from .metrics import PerformanceReport

METRICS = {"sharpe", "total_return_pct", "cagr_pct",
           "profit_factor", "num_trades"}


@dataclass
class OptimizationRun:
    params: dict[str, Any]
    metric: float
    report: PerformanceReport
    regime_blocks: int = 0

    def as_dict(self) -> dict:
        return {"params": self.params, "metric": round(self.metric, 4),
                "regime_blocks": self.regime_blocks,
                "report": self.report.as_dict()}


@dataclass
class WalkForwardFold:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    best_params: dict[str, Any]
    train_metric: float
    test_report: PerformanceReport
    test_metric: float = 0.0

    def as_dict(self) -> dict:
        return {"train": [str(self.train_start), str(self.train_end)],
                "test": [str(self.test_start), str(self.test_end)],
                "best_params": self.best_params,
                "train_metric": round(self.train_metric, 4),
                "test_metric": round(self.test_metric, 4),
                "test_report": self.test_report.as_dict()}


def _run_one(strategy_cls: type[Strategy], params: dict[str, Any],
             symbol: str, ohlcv: pd.DataFrame,
             engine_kwargs: dict[str, Any]) -> OptimizationRun:
    strategy = strategy_cls(**params)
    engine = BacktestEngine(strategy=strategy, symbol=symbol, **engine_kwargs)
    result = engine.run(ohlcv)
    return OptimizationRun(params=params, metric=0.0,
                           report=result.report,
                           regime_blocks=result.regime_blocks)


def _metric_value(report: PerformanceReport, name: str) -> float:
    if name not in METRICS:
        raise ValueError(f"metric must be one of {sorted(METRICS)}, got {name}")
    return float(getattr(report, name))


def _iter_grid(grid: dict[str, Iterable[Any]]) -> Iterable[dict[str, Any]]:
    if not grid:
        yield {}
        return
    keys = list(grid.keys())
    for combo in itertools.product(*[list(v) for v in grid.values()]):
        yield dict(zip(keys, combo))


def grid_search(strategy_cls: type[Strategy], symbol: str,
                ohlcv: pd.DataFrame, param_grid: dict[str, Iterable[Any]],
                metric: str = "sharpe",
                **engine_kwargs: Any) -> list[OptimizationRun]:
    """Evaluate every combination in ``param_grid``; sort by ``metric`` desc."""
    runs: list[OptimizationRun] = []
    for params in _iter_grid(param_grid):
        try:
            run = _run_one(strategy_cls, params, symbol, ohlcv, engine_kwargs)
        except Exception:
            continue
        run.metric = _metric_value(run.report, metric)
        runs.append(run)
    runs.sort(key=lambda r: r.metric, reverse=True)
    return runs


def random_search(strategy_cls: type[Strategy], symbol: str,
                  ohlcv: pd.DataFrame,
                  param_space: dict[str, Iterable[Any]],
                  n_iter: int = 30, seed: int = 0,
                  metric: str = "sharpe",
                  **engine_kwargs: Any) -> list[OptimizationRun]:
    rnd = random.Random(seed)
    spaces = {k: list(v) for k, v in param_space.items()}
    seen: set[tuple] = set()
    runs: list[OptimizationRun] = []
    for _ in range(n_iter):
        params = {k: rnd.choice(vals) for k, vals in spaces.items()}
        key = tuple(sorted(params.items()))
        if key in seen:
            continue
        seen.add(key)
        try:
            run = _run_one(strategy_cls, params, symbol, ohlcv, engine_kwargs)
        except Exception:
            continue
        run.metric = _metric_value(run.report, metric)
        runs.append(run)
    runs.sort(key=lambda r: r.metric, reverse=True)
    return runs


def walk_forward(strategy_cls: type[Strategy], symbol: str,
                 ohlcv: pd.DataFrame, param_grid: dict[str, Iterable[Any]],
                 train_bars: int, test_bars: int,
                 step_bars: int | None = None,
                 metric: str = "sharpe",
                 **engine_kwargs: Any) -> list[WalkForwardFold]:
    """Rolling walk-forward: grid-search on train, evaluate on next test slice."""
    if train_bars <= 0 or test_bars <= 0:
        raise ValueError("train_bars and test_bars must be positive")
    step = step_bars or test_bars
    folds: list[WalkForwardFold] = []
    start = 0
    n = len(ohlcv)
    while start + train_bars + test_bars <= n:
        train = ohlcv.iloc[start: start + train_bars]
        test = ohlcv.iloc[start + train_bars: start + train_bars + test_bars]
        runs = grid_search(strategy_cls, symbol, train, param_grid,
                           metric=metric, **engine_kwargs)
        if not runs:
            start += step
            continue
        best = runs[0]
        test_run = _run_one(strategy_cls, best.params, symbol, test, engine_kwargs)
        test_metric = _metric_value(test_run.report, metric)
        folds.append(WalkForwardFold(
            train_start=train.index[0], train_end=train.index[-1],
            test_start=test.index[0], test_end=test.index[-1],
            best_params=best.params, train_metric=best.metric,
            test_report=test_run.report, test_metric=test_metric,
        ))
        start += step
    return folds


def build_engine_kwargs(starting_cash: float = 10_000.0,
                        risk_per_trade_pct: float = 1.0,
                        warmup: int = 100, timeframe: str = "1h",
                        fee_bps: float = 10.0, slippage_bps: float = 5.0,
                        regime_filter: bool = False,
                        regime_method: str = "rules") -> dict[str, Any]:
    """Helper that mirrors the backtest CLI's engine configuration."""
    return {
        "starting_cash": starting_cash,
        "risk_limits": RiskLimits(max_risk_per_trade_pct=risk_per_trade_pct),
        "warmup": warmup,
        "timeframe": timeframe,
        "cost_model": CostModel(fee_bps=fee_bps, slippage_bps=slippage_bps),
        "regime_filter": (RegimeClassifier(method=regime_method)
                          if regime_filter else None),
    }
