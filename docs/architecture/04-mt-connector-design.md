# MT4/MT5 Connector Architecture

MetaTrader is treated purely as an **execution + data venue** behind a port the
Trading Kernel defines. No trading logic ever runs inside MQL. The connector's job is
narrow and disciplined: move ticks/bars/account state out, move orders in, and never
lie about connection state.

## 1. Interface contract (`core/interfaces/connector.py`)

A single `Connector` Protocol, implemented separately by `connectors/mt4` and
`connectors/mt5` (they differ enough — netting vs. hedging account models, order
semantics, symbol suffixing — to warrant distinct adapters behind the same contract,
per the StockSharp-style "design for many venues even though we only ship one family"
discipline from the repo analysis):

```
Connector(Protocol):
    # lifecycle
    connect() -> None
    disconnect() -> None
    is_connected() -> bool
    on_connection_state_changed: Event[ConnectionState]

    # symbols & data
    subscribe_ticks(symbol) -> None
    subscribe_bars(symbol, timeframe) -> None
    get_symbol_info(symbol) -> SymbolInfo
    get_trade_history(from_ts, to_ts) -> list[Trade]

    # orders & positions
    submit_order(order: OrderRequest) -> OrderAck
    modify_position(position_id, sl=None, tp=None) -> None
    close_position(position_id, volume=None) -> None       # None => full close
    get_open_positions() -> list[Position]

    # account
    get_account_state() -> AccountState   # balance, equity, margin, margin level

    # events emitted onto the Event Bus (not returned synchronously)
    # TickReceived, BarClosed, OrderFilled, OrderRejected, PositionModified,
    # PositionClosed, AccountStateChanged, ConnectionLost, ConnectionRestored
```

`OrderRequest` supports market, pending (limit/stop), and modification requests, and
carries an explicit `account_mode: Netting | Hedging` flag resolved from the connected
account, so upstream Order Manager logic (partial closes, multiple same-symbol
positions) branches on account model rather than assuming one.

## 2. Transport layer

Transport is pluggable behind `connectors/transport/`, so the *protocol* (framing,
message schema, request/response correlation) is decoupled from the *wire mechanism*:

| Transport | Use case | Notes |
|---|---|---|
| **ZeroMQ** (default) | Primary live transport | REQ/REP for command/ack (submit order, modify), PUB/SUB for streaming (ticks, bars, account updates). Two sockets, not one, so a slow command round-trip never backs up the tick stream. |
| **TCP sockets** | Fallback when ZeroMQ isn't available in the deployment environment | Same message schema, raw framed TCP. |
| **WebSockets** | Remote/cloud deployments, browser-facing dashboards needing direct venue state | Same message schema over WS framing. |
| **Named Pipes** | Optional, same-host low-latency (Windows-only MT install) | Lowest latency when kernel and terminal share a machine. |

All four transports carry the **same versioned message schema** (protobuf or
msgpack — decided at implementation time, not architecture time), so swapping
transport is a config change, not a protocol rewrite.

### MT-side bridge
- **MT5**: primary path is a Python-side adapter using the official MetaTrader5
  Python API (`MetaTrader5` package) for account/symbol/order/history calls, paired
  with a lightweight MQL5 Expert Advisor acting purely as a tick/event forwarder
  where the Python API's polling isn't sufficient (sub-second tick streaming) —
  forwarding over the transport layer above, never containing decision logic.
- **MT4**: no official Python API, so the bridge is an MQL4 EA that only (a) forwards
  ticks/bar-closes/account/trade events out over the transport, and (b) receives and
  executes order commands in. Same message schema as MT5, so the rest of the kernel
  is unaware which terminal it's talking to.

## 3. Fault tolerance

- **Heartbeat**: connector sends/expects a heartbeat every N seconds on the PUB/SUB
  channel; missing K consecutive heartbeats flips `ConnectionState` to `Degraded`,
  then `Lost` — published on the Event Bus so the Risk Engine can react (e.g., halt
  new order submission while connection state is not `Connected`).
- **Automatic reconnect** with exponential backoff, capped, resuming subscriptions
  (symbols, timeframes) and re-fetching authoritative state (open positions, account
  balance) from the terminal on reconnect rather than trusting cached state — the
  terminal is always the source of truth for position/order state, the kernel's
  Portfolio Engine is a reconciled mirror, never the authority.
- **Reconciliation pass on reconnect**: diff terminal-reported open positions/orders
  against the kernel's Position Manager state; emit `PositionDiscrepancy` events for
  anything mismatched rather than silently overwriting — an explicit, logged,
  alertable event, never a silent correction.
- **Idempotent order submission**: every `OrderRequest` carries a client-generated
  correlation ID; if a reconnect happens mid-submission, the connector can query "was
  this correlation ID already accepted by the terminal" before resubmitting, avoiding
  duplicate orders.
- **Backpressure on tick stream**: if the kernel-side consumer falls behind, the
  PUB/SUB channel drops to bar-level updates rather than blocking the command channel
  — market data can degrade gracefully; order commands cannot.

## 4. Account/margin/news integration

- `AccountState` polled at a configurable interval and on every relevant event
  (fill, position close) — balance, equity, margin, margin level, drawdown computed
  by the Risk Engine from this stream, not by the connector.
- Economic calendar / news events are **not** sourced from MetaTrader (it has no
  reliable native feed) — ingested via a separate `market_data` provider plugin and
  correlated to symbols by the Signal Engine, published as `NewsEvent` on the same
  bus so strategies/Risk Engine can react (e.g., a pre-news-event liquidity filter).

## 5. Why two adapters, one interface

MT4 and MT5 differ enough (hedging vs. netting-or-hedging account models, MQL4 vs.
MQL5, no official MT4 Python API) that forcing one implementation to cover both would
either leak MT5-only concepts into MT4 or cripple MT5 features to match MT4's
limitations. Two adapters behind one `Connector` Protocol keeps the kernel's dependency
on "a connector" abstract while giving each terminal an implementation honest about
its actual capabilities — directly following the StockSharp-derived discipline of a
narrow, venue-agnostic interface from `02-system-architecture.md`.
