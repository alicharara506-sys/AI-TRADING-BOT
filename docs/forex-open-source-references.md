# Forex / Algorithmic Trading — Open Source References

Reference list of open-source projects relevant to building a Forex trading bot.
Every URL below was verified as live and correct.

| # | Project | URL | Language | License | Stars |
|---|---------|-----|----------|---------|-------|
| 1 | NautilusTrader | https://github.com/nautechsystems/nautilus_trader | Rust (Python bindings via PyO3) | LGPL-3.0 | ~25.3k |
| 2 | QuantConnect LEAN | https://github.com/QuantConnect/Lean | C# + Python | Apache-2.0 | ~21.1k |
| 3 | StockSharp (S#) | https://github.com/StockSharp/StockSharp | C# | Open source (see repo LICENSE) | ~10.5k |
| 4 | Backtrader | https://github.com/mementum/backtrader | Python | GPL-3.0 | ~22.7k |
| 5 | backtesting.py | https://github.com/kernc/backtesting.py | Python | AGPL-3.0 | ~8.8k |
| 6 | EA31337 | https://github.com/EA31337/EA31337 | MQL4/MQL5 | GPL-3.0 | ~1.3k |
| 7 | exchange-api | https://github.com/fawazahmed0/exchange-api | JSON data / CDN | Open data | ~2.5k |
| 8 | QuantDinger | https://github.com/OpenByteInc/QuantDinger | Python 3.12 | Open source | ~10.3k |

Star counts are approximate, captured at the time this file was written.

## Notes

### 1. NautilusTrader
Production-grade, Rust-native engine for multi-asset, multi-venue trading systems.
Research, simulation, and live execution share one event-driven architecture, so the
same strategy code runs in backtest and in production. Deterministic backtesting;
venues and data providers are added through modular adapters.

**Fit:** the strongest choice if we want one codebase from backtest to live, and can
live with LGPL-3.0 plus a Rust/Python toolchain.

### 2. QuantConnect LEAN
Event-driven algorithmic trading platform. Backtesting, live trading, a research
environment, and parameter optimization. Strategies are written in C# or Python.
Apache-2.0 makes it the most permissive license in this list.

**Fit:** best licensing story and a mature hosted ecosystem (QuantConnect Cloud) if we
ever want to offload infrastructure.

### 3. StockSharp (S#)
Trading platform covering crypto, FX, equities, futures, and options, with 200+ market
connections. Ships as a suite — Designer, Hydra, Terminal, Shell — plus a C# API.

**Fit:** relevant mainly for its breadth of broker/venue connectors. .NET-centric.

### 4. Backtrader
Long-established Python backtesting library, 122 built-in indicators, broker simulation,
analyzers, plotting. Live feeds/trading for Interactive Brokers, Visual Chart, and Oanda
(Oanda being the FX-relevant one).

**Caveat:** upstream development has been largely dormant for years despite the high star
count. Treat it as stable-but-frozen rather than actively maintained; community forks
exist if we need fixes.

### 5. backtesting.py
Small, fast backtesting library for OHLC candlestick data with a simple API and a
built-in optimizer. Deliberately narrow in scope — backtesting only, no live execution.

**Caveat:** AGPL-3.0. If any of our code is network-served and links this, the copyleft
reaches it. Worth a licensing decision before adopting.

### 6. EA31337
Free and open-source Forex trading robot for MetaTrader 4 and 5. Dozens of pre-built
strategies, risk management, and heavy parameterization.

**Fit:** the only MT4/MT5-native entry here — useful as a source of concrete FX strategy
logic and risk-management patterns, even if we don't run MetaTrader ourselves.

### 7. exchange-api (fawazahmed0)
Free currency exchange rate API — 200+ currencies including major cryptocurrencies and
metals, updated daily, no rate limits, served over jsDelivr CDN with a Cloudflare Pages
fallback. Endpoints for current rates by base currency and for historical dates
(`YYYY-MM-DD`), in both standard and minified JSON.

**Caveat:** daily granularity only. Fine for reference/conversion rates and historical
context; not a substitute for a tick or intraday feed in an execution path.

### 8. QuantDinger
Self-hosted "AI trading OS" — turns strategy ideas into Python strategies, backtests,
paper trading, live execution, and monitoring in one stack. Multi-provider AI market
research, crypto exchange and traditional broker support, web and mobile interfaces.
Local-first: strategy code, broker credentials, and market data stay on our
infrastructure.

**Fit:** closest in shape to the end-to-end product we're building; worth reading for
architecture even if we don't adopt it wholesale.

## Licensing summary

Before pulling any of these in, note the copyleft split:

- **Permissive:** LEAN (Apache-2.0) — safe to link and redistribute.
- **GPL-3.0:** Backtrader, EA31337 — distributing a derived binary/source obligates us
  to release under GPL.
- **LGPL-3.0:** NautilusTrader — linking is permitted; modifications to the library
  itself must be shared.
- **AGPL-3.0:** backtesting.py — the network-use clause makes this the most demanding
  for a hosted bot.
