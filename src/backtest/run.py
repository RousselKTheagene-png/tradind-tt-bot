"""CLI entry point for backtesting: `python -m src.backtest.run ...`."""
from __future__ import annotations

import argparse
import json
import os

from dotenv import load_dotenv

from ..data.crypto_provider import CryptoProvider
from ..execution.cost_model import CostModel
from ..intelligence.regime import RegimeClassifier
from ..main import STRATEGY_REGISTRY
from ..risk.risk_manager import RiskLimits
from .engine import BacktestEngine


def _fetch_ohlcv(exchange: str, symbol: str, timeframe: str, limit: int):
    provider = CryptoProvider(
        exchange=exchange,
        api_key=os.getenv("BINANCE_API_KEY", ""),
        api_secret=os.getenv("BINANCE_API_SECRET", ""),
    )
    return provider.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run a strategy backtest")
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--limit", type=int, default=1000,
                        help="Number of historical bars to fetch")
    parser.add_argument("--strategy", default="ema_crossover",
                        choices=list(STRATEGY_REGISTRY.keys()))
    parser.add_argument("--cash", type=float, default=10_000.0)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--risk-per-trade", type=float, default=1.0)
    parser.add_argument("--fee-bps", type=float, default=10.0,
                        help="Per-trade fee in basis points (default 10 bps = 0.10%%)")
    parser.add_argument("--slippage-bps", type=float, default=5.0,
                        help="Per-fill slippage in basis points (default 5 bps = 0.05%%)")
    parser.add_argument("--regime-filter", action="store_true",
                        help="Only allow strategies to fire in their tolerated regimes")
    parser.add_argument("--regime-method", choices=["rules", "kmeans"], default="rules")
    parser.add_argument("--params", default="{}",
                        help="JSON dict of strategy params, e.g. '{\"fast\":10}'")
    parser.add_argument("--csv", help="Optional path to a CSV with OHLCV instead of live fetch")
    args = parser.parse_args()

    params = json.loads(args.params)
    strat_cls = STRATEGY_REGISTRY[args.strategy]
    strategy = strat_cls(**params)

    if args.csv:
        import pandas as pd
        ohlcv = pd.read_csv(args.csv, parse_dates=["timestamp"], index_col="timestamp")
    else:
        ohlcv = _fetch_ohlcv(args.exchange, args.symbol, args.timeframe, args.limit)

    regime_filter = RegimeClassifier(method=args.regime_method) if args.regime_filter else None

    engine = BacktestEngine(
        strategy=strategy,
        symbol=args.symbol,
        starting_cash=args.cash,
        risk_limits=RiskLimits(max_risk_per_trade_pct=args.risk_per_trade),
        warmup=args.warmup,
        timeframe=args.timeframe,
        cost_model=CostModel(fee_bps=args.fee_bps, slippage_bps=args.slippage_bps),
        regime_filter=regime_filter,
    )
    result = engine.run(ohlcv)

    regime_tag = f"  Regime filter: {args.regime_method}" if args.regime_filter else ""
    print(f"\n=== Backtest: {args.strategy} on {args.symbol} {args.timeframe} ===")
    print(f"Bars: {len(ohlcv)}  Trades: {result.report.num_trades}  "
          f"Fees: {args.fee_bps}bps  Slippage: {args.slippage_bps}bps{regime_tag}")
    for k, v in result.report.as_dict().items():
        print(f"  {k:<20} {v}")
    print(f"  {'total_fees_paid':<20} {engine.broker.total_fees_paid:.4f}")
    if args.regime_filter:
        print(f"  {'regime_blocks':<20} {result.regime_blocks}")


if __name__ == "__main__":
    main()
