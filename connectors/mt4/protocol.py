from __future__ import annotations

# Action names for the REQ/REP command channel between MT4Connector (Python)
# and the companion MQL4 Expert Advisor. The EA is a thin forwarder: it
# executes exactly these actions and returns a JSON reply, with no trading
# decision logic of its own.

ACTION_CONNECT = "connect"
ACTION_DISCONNECT = "disconnect"
ACTION_SUBSCRIBE_TICKS = "subscribe_ticks"
ACTION_SUBSCRIBE_BARS = "subscribe_bars"
ACTION_SUBMIT_ORDER = "submit_order"
ACTION_MODIFY_POSITION = "modify_position"
ACTION_CLOSE_POSITION = "close_position"
ACTION_GET_ACCOUNT_STATE = "get_account_state"
ACTION_GET_SYMBOL_INFO = "get_symbol_info"
ACTION_GET_OPEN_POSITIONS = "get_open_positions"
ACTION_GET_TRADE_HISTORY = "get_trade_history"

# Topics on the PUB/SUB market-data channel the EA streams out on.
TOPIC_TICK = "tick"
TOPIC_BAR = "bar"

__all__ = [
    "ACTION_CLOSE_POSITION",
    "ACTION_CONNECT",
    "ACTION_DISCONNECT",
    "ACTION_GET_ACCOUNT_STATE",
    "ACTION_GET_OPEN_POSITIONS",
    "ACTION_GET_SYMBOL_INFO",
    "ACTION_GET_TRADE_HISTORY",
    "ACTION_MODIFY_POSITION",
    "ACTION_SUBMIT_ORDER",
    "ACTION_SUBSCRIBE_BARS",
    "ACTION_SUBSCRIBE_TICKS",
    "TOPIC_BAR",
    "TOPIC_TICK",
]
