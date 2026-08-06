from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from core.interfaces.clock import Clock
from core.kernel.clock import LiveClock


def compute_experiment_id(
    *, kind: str, subject_name: str, parameters: Mapping[str, Any]
) -> str:
    """Deterministic composite key over (kind, subject_name, parameters) --
    the same trial run twice hashes to the same id, which is what makes
    ExperimentLog.record() idempotent. Mirrors nof1-tracker's
    entryOid+symbol dedup guard, translated from "don't double-execute an
    order" to "don't double-count a trial."
    """
    canonical = json.dumps(
        {"kind": kind, "subject_name": subject_name, "parameters": parameters},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class ExperimentRecord:
    """One research experiment's full provenance: what was run, on what
    subject, with what parameters, what came out, and why it was run at all
    (the hypothesis) -- everything needed to reproduce or audit it later.
    """

    experiment_id: str
    kind: str
    subject_name: str
    parameters: dict[str, Any]
    outcome: dict[str, Any]
    recorded_at: datetime
    hypothesis: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _record_to_dict(record: ExperimentRecord) -> dict[str, Any]:
    return {
        "experiment_id": record.experiment_id,
        "kind": record.kind,
        "subject_name": record.subject_name,
        "parameters": record.parameters,
        "outcome": record.outcome,
        "recorded_at": record.recorded_at.isoformat(),
        "hypothesis": record.hypothesis,
        "metadata": record.metadata,
    }


def _record_from_dict(payload: dict[str, Any]) -> ExperimentRecord:
    return ExperimentRecord(
        experiment_id=payload["experiment_id"],
        kind=payload["kind"],
        subject_name=payload["subject_name"],
        parameters=payload["parameters"],
        outcome=payload["outcome"],
        recorded_at=datetime.fromisoformat(payload["recorded_at"]),
        hypothesis=payload.get("hypothesis"),
        metadata=payload.get("metadata", {}),
    )


class ExperimentLog:
    """An append-only, replayable log of research experiments.

    State is reconstructed by replaying the log file from scratch on
    construction rather than trusting any cached in-memory state across
    process restarts -- the same "state rebuilt from an append-only log"
    discipline nof1-tracker's OrderHistoryManager uses to survive crashes,
    applied here to backtest/optimization/validation runs instead of order
    history. Re-recording an experiment with identical (kind, subject_name,
    parameters) is idempotent: the existing record is returned unchanged
    rather than appended again, so re-running an interrupted sweep never
    double-counts a trial it already completed.
    """

    def __init__(self, *, path: Path | None = None, clock: Clock | None = None) -> None:
        self._clock = clock or LiveClock()
        self._path = path
        self._records: dict[str, ExperimentRecord] = {}
        self._order: list[str] = []
        if path is not None and path.exists():
            self._replay(path)

    def _replay(self, path: Path) -> None:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = _record_from_dict(json.loads(line))
            if record.experiment_id not in self._records:
                self._order.append(record.experiment_id)
            self._records[record.experiment_id] = record

    def record(
        self,
        *,
        kind: str,
        subject_name: str,
        parameters: Mapping[str, Any],
        outcome: Mapping[str, Any],
        hypothesis: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[ExperimentRecord, bool]:
        """Returns (record, is_new). is_new is False when an identical
        experiment was already recorded -- the existing record is returned,
        nothing is appended twice.
        """
        experiment_id = compute_experiment_id(
            kind=kind, subject_name=subject_name, parameters=parameters
        )
        existing = self._records.get(experiment_id)
        if existing is not None:
            return existing, False

        record = ExperimentRecord(
            experiment_id=experiment_id,
            kind=kind,
            subject_name=subject_name,
            parameters=dict(parameters),
            outcome=dict(outcome),
            recorded_at=self._clock.now(),
            hypothesis=hypothesis,
            metadata=dict(metadata or {}),
        )
        self._records[experiment_id] = record
        self._order.append(experiment_id)
        if self._path is not None:
            self._append_to_file(self._path, record)
        return record, True

    def _append_to_file(self, path: Path, record: ExperimentRecord) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_record_to_dict(record)) + "\n")

    def history(self) -> tuple[ExperimentRecord, ...]:
        return tuple(self._records[experiment_id] for experiment_id in self._order)

    def by_subject(self, subject_name: str) -> tuple[ExperimentRecord, ...]:
        return tuple(r for r in self.history() if r.subject_name == subject_name)

    def by_kind(self, kind: str) -> tuple[ExperimentRecord, ...]:
        return tuple(r for r in self.history() if r.kind == kind)

    def best(
        self, subject_name: str, *, outcome_key: str, higher_is_better: bool = True
    ) -> ExperimentRecord:
        """Ranks only among records that actually carry `outcome_key` --
        a subject can accumulate heterogeneous experiment kinds (e.g. both
        optimization_trial and validation_report records), and those don't
        share an outcome shape, so a record missing the requested key is
        excluded rather than crashing the whole selection.
        """
        all_records = self.by_subject(subject_name)
        if not all_records:
            raise ValueError(f"no experiments recorded for subject '{subject_name}'")
        candidates = [r for r in all_records if outcome_key in r.outcome]
        if not candidates:
            raise ValueError(
                f"no experiments for subject '{subject_name}' carry outcome key '{outcome_key}'"
            )
        selector = max if higher_is_better else min
        return selector(candidates, key=lambda r: r.outcome[outcome_key])


__all__ = ["ExperimentLog", "ExperimentRecord", "compute_experiment_id"]
