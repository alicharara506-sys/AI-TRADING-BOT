"""Macro/economic data: a provider-agnostic fetch layer (macro_data.provider,
macro_data.providers.fred) for real macro time series (FRED to start).

Deliberately data-layer only for now -- no AnalysisModule here votes on a
macro reading. A real, honest directional module needs a specific,
research-backed claim about how a given series maps to a given symbol's
direction (e.g. "does the 10Y-2Y curve inverting predict EURUSD direction,
and by how much, and over what horizon?"), and this platform has no
backtested validation for any such claim yet -- fabricating one would be
exactly the kind of unsupported number this project's verification
discipline exists to prevent (see decision_engine's own "deliberately not
built" section, docs/architecture/09-decision-engine.md). Once a specific
macro/symbol relationship is validated against real history, it becomes a
real AnalysisModule the same way every other one here did.
"""
