# Trading Bot

A multi-market algorithmic trading bot for **stocks, crypto, and forex**.
Designed to run 24/7 with pluggable strategies, risk management, and
both paper and live execution modes.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Main Loop                          │
└──────────────┬──────────────────────────┬───────────────┘
               │                          │
        ┌──────▼──────┐            ┌──────▼──────┐
        │ Data Layer  │            │ Intelligence│
        │ (live/hist) │            │ (regime/ML) │
        └──────┬──────┘            └──────┬──────┘
               │                          │
               └─────────┬────────────────┘
                         │
                 ┌───────▼────────┐
                 │ Strategy Engine│
                 │ (TA, patterns) │
                 └───────┬────────┘
                         │
                 ┌───────▼────────┐
                 │ Risk Manager   │
                 │ (sizing, stops)│
                 └───────┬────────┘
                         │
                 ┌───────▼────────┐
                 │ Execution      │
                 │ (paper / live) │
                 └───────┬────────┘
                         │
                 ┌───────▼────────┐
                 │ Monitoring     │
                 │ (journal, P&L) │
                 └────────────────┘
```

## Modules

| Path | Purpose |
|---|---|
| `src/data/` | Market data providers (crypto, stock, forex) |
| `src/strategies/` | Indicators, patterns, strategy implementations |
| `src/risk/` | Position sizing and risk management |
| `src/execution/` | Order routing (paper broker, live brokers) |
| `src/intelligence/` | Regime detection, sentiment analysis, ML |
| `src/monitoring/` | Logging, trade journal, performance analytics |
| `src/backtest/` | Historical backtesting engine |
| `config/` | Strategy and risk configuration |
| `tests/` | Unit and integration tests |

## Supported Markets (planned)

- **Crypto:** Binance, Coinbase (via `ccxt`)
- **Stocks:** Alpaca (paper + live)
- **Forex:** OANDA

## Getting Started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m src.main --mode paper --config config/config.yaml
```

## Safety First

- Default mode is **paper trading**. Live trading requires explicit
  `--mode live` and non-empty broker credentials.
- Risk manager enforces per-trade, per-day, and max-drawdown limits.
- All trades are logged to a persistent journal.

## Roadmap

- [x] Project scaffold
- [x] Data providers (crypto, stocks, forex)
- [x] Indicator library
- [x] Strategy base + example strategies
  (EMA crossover, Donchian breakout, Bollinger squeeze, RSI reversion,
  Supertrend, MACD divergence, RSI / MACD confluence)
- [x] Risk manager
- [x] Paper broker
- [x] Backtest engine (with walk-forward optimizer)
- [x] Live broker adapters (Alpaca, ccxt, OANDA)
- [ ] ML regime classifier
- [ ] Sentiment pipeline
- [x] Monitoring dashboard
