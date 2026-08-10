"""Live signal lifecycle tracking: watches already-generated DecisionReports
against real MT5 ticks and records what actually happened (trigger, TP1-3,
SL, expiry) as a SignalOutcome, closing the loop that OutcomeAnalytics and
the calibration gate need real resolved trades to exist at all.
"""
