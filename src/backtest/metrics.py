"""Performance metrics for a backtest run."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# Approximate periods-per-year for annualization of the Sharpe ratio.
PERIODS_PER_YEAR = {
    "1m": 525_600, "5m": 105_120, "15m": 35_040, "30m": 17_520,
    "1h": 8_760, "4h": 2_190, "1d": 365, "1w": 52,
}


@dataclass
class PerformanceReport:
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    max_drawdown_pct: float
    win_rate_pct: float
    profit_factor: float
    num_trades: int
    avg_trade_pnl: float

    def as_dict(self) -> dict:
        return {
            "total_return_pct": round(self.total_return_pct, 4),
            "cagr_pct": round(self.cagr_pct, 4),
            "sharpe": round(self.sharpe, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 4),
            "win_rate_pct": round(self.win_rate_pct, 4),
            "profit_factor": round(self.profit_factor, 4),
            "num_trades": self.num_trades,
            "avg_trade_pnl": round(self.avg_trade_pnl, 4),
        }


def _max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    drawdown = (equity - peak) / peak
    return float(drawdown.min())


def _sharpe(returns: pd.Series, timeframe: str) -> float:
    if returns.std() == 0 or returns.empty:
        return 0.0
    ann = PERIODS_PER_YEAR.get(timeframe, 252)
    return float(returns.mean() / returns.std() * np.sqrt(ann))


def _cagr(equity: pd.Series, timeframe: str) -> float:
    if len(equity) < 2:
        return 0.0
    ann = PERIODS_PER_YEAR.get(timeframe, 252)
    years = len(equity) / ann
    if years <= 0:
        return 0.0
    return float((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1)


def compute_metrics(
    equity_curve: pd.Series,
    trade_pnls: list[float],
    timeframe: str = "1h",
) -> PerformanceReport:
    if equity_curve.empty:
        return PerformanceReport(0, 0, 0, 0, 0, 0, 0, 0)

    returns = equity_curve.pct_change().dropna()
    total_return = float(equity_curve.iloc[-1] / equity_curve.iloc[0] - 1)
    wins = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p < 0]
    win_rate = len(wins) / len(trade_pnls) if trade_pnls else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0

    return PerformanceReport(
        total_return_pct=total_return * 100,
        cagr_pct=_cagr(equity_curve, timeframe) * 100,
        sharpe=_sharpe(returns, timeframe),
        max_drawdown_pct=_max_drawdown(equity_curve) * 100,
        win_rate_pct=win_rate * 100,
        profit_factor=pf,
        num_trades=len(trade_pnls),
        avg_trade_pnl=float(np.mean(trade_pnls)) if trade_pnls else 0.0,
    )
