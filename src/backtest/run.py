"""CLI entry point for backtesting: `python -m src.backtest.run ...`."""
from __future__ import annotations

import argparse
import json
import os

from dotenv import load_dotenv

from ..data.crypto_provider import CryptoProvider
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

    engine = BacktestEngine(
        strategy=strategy,
        symbol=args.symbol,
        starting_cash=args.cash,
        risk_limits=RiskLimits(max_risk_per_trade_pct=args.risk_per_trade),
        warmup=args.warmup,
        timeframe=args.timeframe,
    )
    result = engine.run(ohlcv)

    print(f"\n=== Backtest: {args.strategy} on {args.symbol} {args.timeframe} ===")
    print(f"Bars: {len(ohlcv)}  Trades: {result.report.num_trades}")
    for k, v in result.report.as_dict().items():
        print(f"  {k:<20} {v}")


if __name__ == "__main__":
    main()
