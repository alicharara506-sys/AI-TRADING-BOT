"""Commitments of Traders (COT) positioning data: a provider-agnostic
fetch layer (cot_data.provider, cot_data.providers.cftc) for the CFTC's
free, public weekly COT reports.

Deliberately data-layer only for now -- no AnalysisModule here votes on a
COT reading. Large-speculator/commercial positioning is a widely-cited
sentiment heuristic (e.g. "fade an extreme non-commercial net-long"), but
this platform has no backtested validation for any specific positioning
threshold or lookback on any specific symbol yet -- fabricating one would
be exactly the kind of unsupported number this project's verification
discipline exists to prevent (see macro_data's own "deliberately not
built" precedent, macro_data/__init__.py, and decision_engine's,
docs/architecture/09-decision-engine.md). Once a specific positioning
relationship is validated against real history, it becomes a real
AnalysisModule the same way every other one here did.
"""
