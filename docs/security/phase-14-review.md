# Phase 14 security review

Scope: credential handling, input validation at external boundaries
(MT4/MT5 wire protocol, webhook payloads), and a dependency audit. This is
a point-in-time review, not a certification -- re-run the checks below
whenever a new external boundary or dependency is added.

## Credential handling

- MT5 `login`/`password`/`server` are plain constructor arguments on
  `MT5Connector` (`connectors/mt5/connector.py`). Grepped the entire
  non-test codebase for `password`: it is stored on `self._password` and
  passed straight through to `MT5Api.login(...)`; it is never interpolated
  into a log line, exception message, or `f"{...}"` string. `ConnectionError`
  messages on login/initialize failure only include `code`/`message` from
  `MT5Api.last_error()`, which originates from the API, not from the
  credential values.
- `core/config/settings.py` layers defaults -> YAML file -> `KERNEL_*`
  environment variables, and nothing under `core/` or `connectors/` reads
  credentials from a committed file. Grepped tracked `*.yaml`/`*.yml`/
  `*.json`/`*.ini`/`*.toml` files for `password|secret|api[_-]?key|token`:
  zero matches. No secrets are committed anywhere in the repository today.
- Hardened `.gitignore` to explicitly exclude `.env`, `.env.*`,
  `*.local.yaml`/`*.local.yml`, and `secrets.yaml`/`secrets.yml` so future
  operator-supplied credential files can't be committed by accident --
  previously only build artifacts and caches were excluded.
- **Recommendation for future work**: when MT5/MT4 credentials move from
  test-only constructor args to a real deployment path, load them via
  `KERNEL_*` environment variables (already supported by
  `core/config/settings.py`) or a gitignored local file -- never a file
  intended to be committed.

## Input validation at external boundaries

- **ZeroMQ command/market-data channel (MT4) -- no authentication or
  encryption.** `ZmqRequester`/`ZmqReplier`/`ZmqPublisher`/`ZmqSubscriber`
  (`connectors/transport/zeromq.py`) use plaintext TCP with no CURVE
  authentication and no TLS. Anyone who can reach the bound TCP port can
  submit orders through the command channel or read the market-data
  stream. This is the most significant finding in this review. It is a
  deployment-topology risk, not fixed by this pass: the command/market-data
  processes (the Python kernel and the MT4 EA bridge) must run on a
  private network segment (localhost, a VPN, or an SSH tunnel) rather than
  a publicly reachable address. Adding ZMQ CURVE authentication is real
  future work, tracked here rather than attempted as a drive-by change in
  a hardening pass whose other goals are chaos-testing and benchmarking.
- **Unbounded message size (fixed this pass).** None of the four ZeroMQ
  socket wrappers capped incoming message size, so a malformed or hostile
  peer could send an arbitrarily large frame. Added
  `zmq.MAXMSGSIZE` (1 MiB, comfortably above any real tick/bar/order JSON
  payload) to every socket in `connectors/transport/zeromq.py`. Verified
  the existing 48 connector tests still pass unchanged.
- **REQ socket left unusable after a timeout (fixed this pass, see Phase 14
  chaos-testing work).** `ZmqRequester` now recreates its socket after a
  timeout instead of leaving it permanently stuck mid-handshake -- see the
  connector fault-tolerance test suite
  (`tests/integration/test_connector_fault_tolerance.py`) for the
  regression proof.
- **Malformed wire payloads fail loudly, not silently.** `MT4Connector`'s
  `_parse_tick`/`_parse_bar`/`_parse_position`/`_parse_trade` use direct
  dict indexing (`payload["bid"]`, etc.), so a payload missing an expected
  field raises `KeyError` rather than silently constructing a bad `Tick`/
  `Bar`/`Position`/`Trade`. This is the correct default for a boundary
  where malformed data indicates a bug in the companion EA and should stop
  processing, not paper over it -- but it means a single malformed message
  can crash the `listen()` loop. Full wire-protocol schema validation
  (e.g. a pydantic model per message type) would change this from "loop
  dies, needs a supervisor to restart it" to "one bad message is skipped
  and logged" -- flagged as future work, out of scope for this pass.
- **WebhookNotifier scheme validation (fixed this pass).**
  `WebhookNotifier.__init__` previously only rejected an empty URL. Added a
  scheme check that rejects anything other than `http`/`https` (e.g.
  `file://`, `ftp://`, `javascript:`), since `urllib.request` will attempt
  to honor whatever scheme it's given. Regression test:
  `test_webhook_notifier_rejects_non_http_schemes` in
  `tests/unit/notifications/test_notifier.py`.
- **Webhook payload encoding.** `WebhookNotifier` builds its POST body with
  `json.dumps(...)`, so operator-supplied `subject`/`body` text is properly
  escaped -- no injection risk into the JSON structure itself.

## Dependency audit

Ran `pip-audit --local` against the installed environment. It reported 38
findings across 8 packages (`cryptography`, `httplib2`, `idna`, `pip`,
`pyjwt`, `setuptools`, `urllib3`, `wheel`), but **none of them are
dependencies of this project**: cross-checked `pip show <pkg> | grep
Requires` for every package this project actually declares (`pydantic`,
`pyyaml`, `pyarrow`, `pyzmq`, `numpy`, `statsmodels`, `scikit-learn`,
`pytest`, `pytest-asyncio`, `mypy`, `ruff`, `types-PyYAML`) and none of
them require any of the flagged packages, directly or transitively. The
flagged packages are pre-existing environment/system tooling unrelated to
`ai-trading-bot`'s own dependency graph.

**Result: zero known vulnerabilities in this project's actual dependency
tree.** Re-run `pip-audit --local` and re-check each flagged package
against `pyproject.toml`'s `[project.dependencies]` after any dependency
change, the same way this review did.
