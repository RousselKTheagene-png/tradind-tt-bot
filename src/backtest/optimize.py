"""CLI for strategy parameter optimization.

Usage:
    python -m src.backtest.optimize \
        --strategy ema_crossover --symbol BTC/USDT --timeframe 1h --limit 2000 \
        --param-grid '{"fast":[10,20,30],"slow":[50,100,200]}' --metric sharpe

    python -m src.backtest.optimize ... --walk-forward \
        --train-bars 800 --test-bars 200 --step-bars 200
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from ..data.crypto_provider import CryptoProvider
from ..main import STRATEGY_REGISTRY
from .optimizer import (build_engine_kwargs, grid_search, random_search,
                        walk_forward)


def _load_ohlcv(args):
    if args.csv:
        import pandas as pd
        return pd.read_csv(args.csv, parse_dates=["timestamp"], index_col="timestamp")
    exch = args.exchange
    key_env = f"{exch.upper()}_API_KEY"
    secret_env = f"{exch.upper()}_API_SECRET"
    provider = CryptoProvider(exchange=exch,
                              api_key=os.getenv(key_env, ""),
                              api_secret=os.getenv(secret_env, ""))
    return provider.fetch_ohlcv(args.symbol, timeframe=args.timeframe,
                                limit=args.limit)


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Parameter optimizer")
    parser.add_argument("--strategy", required=True,
                        choices=list(STRATEGY_REGISTRY.keys()))
    parser.add_argument("--symbol", default="BTC/USDT")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--limit", type=int, default=1500)
    parser.add_argument("--csv")
    parser.add_argument("--param-grid", required=True,
                        help='JSON e.g. \'{"fast":[10,20],"slow":[50,100]}\'')
    parser.add_argument("--mode", choices=["grid", "random", "walk-forward"],
                        default="grid")
    parser.add_argument("--n-iter", type=int, default=30,
                        help="iterations for random search")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--train-bars", type=int, default=800)
    parser.add_argument("--test-bars", type=int, default=200)
    parser.add_argument("--step-bars", type=int, default=200)
    parser.add_argument("--metric", default="sharpe",
                        choices=["sharpe", "total_return_pct", "cagr_pct",
                                 "profit_factor", "num_trades"])
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--cash", type=float, default=10_000.0)
    parser.add_argument("--risk-per-trade", type=float, default=1.0)
    parser.add_argument("--warmup", type=int, default=100)
    parser.add_argument("--fee-bps", type=float, default=10.0)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--regime-filter", action="store_true")
    parser.add_argument("--regime-method", choices=["rules", "kmeans"],
                        default="rules")
    parser.add_argument("--out", help="Write JSON report to this path")
    args = parser.parse_args()

    grid = json.loads(args.param_grid)
    strat_cls = STRATEGY_REGISTRY[args.strategy]
    ohlcv = _load_ohlcv(args)

    engine_kwargs = build_engine_kwargs(
        starting_cash=args.cash, risk_per_trade_pct=args.risk_per_trade,
        warmup=args.warmup, timeframe=args.timeframe,
        fee_bps=args.fee_bps, slippage_bps=args.slippage_bps,
        regime_filter=args.regime_filter, regime_method=args.regime_method,
    )

    header = f"=== Optimize {args.strategy} on {args.symbol} {args.timeframe} " \
             f"({len(ohlcv)} bars, metric={args.metric}) ==="
    print(header)

    out_payload: dict = {"strategy": args.strategy, "symbol": args.symbol,
                         "timeframe": args.timeframe, "bars": len(ohlcv),
                         "metric": args.metric, "mode": args.mode}

    if args.mode == "walk-forward":
        folds = walk_forward(strat_cls, args.symbol, ohlcv, grid,
                             train_bars=args.train_bars,
                             test_bars=args.test_bars,
                             step_bars=args.step_bars,
                             metric=args.metric, **engine_kwargs)
        print(f"Walk-forward: {len(folds)} folds")
        for i, f in enumerate(folds):
            print(f"  fold {i:02d}  params={f.best_params}  "
                  f"train={f.train_metric:.3f}  test={f.test_metric:.3f}  "
                  f"return={f.test_report.total_return_pct:.2f}%")
        out_payload["folds"] = [f.as_dict() for f in folds]
    else:
        if args.mode == "random":
            runs = random_search(strat_cls, args.symbol, ohlcv, grid,
                                 n_iter=args.n_iter, seed=args.seed,
                                 metric=args.metric, **engine_kwargs)
        else:
            runs = grid_search(strat_cls, args.symbol, ohlcv, grid,
                               metric=args.metric, **engine_kwargs)
        print(f"Evaluated {len(runs)} configurations. Top {args.top}:")
        for i, r in enumerate(runs[:args.top]):
            d = r.report.as_dict()
            print(f"  {i:02d}  {args.metric}={r.metric:>8.3f}  "
                  f"return={d['total_return_pct']:>7.2f}%  "
                  f"dd={d['max_drawdown_pct']:>7.2f}%  "
                  f"trades={d['num_trades']:>3d}  params={r.params}")
        out_payload["runs"] = [r.as_dict() for r in runs]

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out_payload, indent=2,
                                             default=str))
        print(f"Wrote report to {args.out}")


if __name__ == "__main__":
    main()
