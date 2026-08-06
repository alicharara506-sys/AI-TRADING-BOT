from __future__ import annotations

import statistics

from research_lab.experiment_log import ExperimentLog


def render_subject_report(
    log: ExperimentLog, subject_name: str, *, outcome_key: str, higher_is_better: bool = True
) -> str:
    """Automatic report generation over every experiment recorded for one
    subject: how many runs, the best one found, and the spread of outcomes
    -- the minimum an operator needs to trust a sweep's result without
    re-deriving it from the raw log by hand.
    """
    records = log.by_subject(subject_name)
    if not records:
        return f"Experiment report: {subject_name}\n  No experiments recorded."

    values = [r.outcome[outcome_key] for r in records if outcome_key in r.outcome]
    best = log.best(subject_name, outcome_key=outcome_key, higher_is_better=higher_is_better)

    runs_line = f"  Runs: {len(records)} total"
    if len(values) != len(records):
        # A subject can accumulate heterogeneous experiment kinds (e.g. both
        # optimization trials and validation reports); only some of them
        # carry this particular outcome key.
        runs_line += f" ({len(values)} carrying '{outcome_key}')"

    lines = [
        f"Experiment report: {subject_name}",
        runs_line,
        f"  Best {outcome_key}: {best.outcome[outcome_key]:.6g} "
        f"(experiment {best.experiment_id}, kind={best.kind})",
        f"  Best parameters: {best.parameters}",
    ]
    if best.hypothesis:
        lines.append(f"  Hypothesis: {best.hypothesis}")
    if len(values) >= 2:
        lines.append(
            f"  {outcome_key} across all runs: mean={statistics.mean(values):.6g} "
            f"stdev={statistics.stdev(values):.6g} "
            f"min={min(values):.6g} max={max(values):.6g}"
        )
    return "\n".join(lines)


__all__ = ["render_subject_report"]
