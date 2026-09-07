"""Export report artifacts from Inspect eval logs.

The Inspect log is the source of truth for native runs.  This module deliberately
uses :mod:`inspect_ai.log` rather than opening the compressed ``.eval`` files
itself, so exported reports remain compatible with Inspect log-format changes.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_NO_REPORT = "(no report written)"


def _safe_name(value: object) -> str:
    return _SAFE_NAME.sub("_", str(value)).strip("_") or "unknown"


def _prompt_text(value: object) -> str:
    """Return a stable text form of a sample input without assuming its type."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(getattr(item, "content", item)) for item in value)
    return str(value or "")


@dataclass(frozen=True)
class ExportRecord:
    """One report recovered from an Inspect sample."""

    report: str
    prompt: str
    metadata: dict[str, Any]
    log_file: str
    sample_id: str
    epoch: int
    partial: bool


def records_from_log(
    log: Any, log_file: str, *, backend: str | None
) -> list[ExportRecord]:
    """Read report-bearing samples from an already decoded Inspect log.

    ``backend=None`` accepts all MessageBoardAuditBench logs.  The native
    exporter defaults to ``inspect`` so imported subscription runs cannot be
    accidentally mixed with live Inspect SWE trajectories.
    """
    records: list[ExportRecord] = []
    for sample in log.samples or []:
        metadata = dict(getattr(sample, "metadata", {}) or {})
        output = getattr(sample, "output", None)
        # Native task metadata deliberately records the harness rather than
        # duplicating Inspect's selected model. Preserve that model in the
        # artifact index when the task did not add one itself.
        if not metadata.get("model"):
            metadata["model"] = getattr(output, "model", None) or getattr(
                getattr(log, "eval", None), "model", None
            )
        sample_backend = metadata.get("backend")
        if backend is not None and sample_backend != backend:
            continue
        report = str(getattr(output, "completion", "") or "")
        if not report or report == _NO_REPORT:
            continue
        prompt = _prompt_text(getattr(sample, "input", ""))
        records.append(
            ExportRecord(
                report=report,
                prompt=prompt,
                metadata=metadata,
                log_file=log_file,
                sample_id=str(getattr(sample, "id", "unknown")),
                epoch=int(getattr(sample, "epoch", 0)),
                partial=bool(
                    getattr(sample, "error", None)
                    or metadata.get("trial_failed")
                    or metadata.get("exit_code") not in (None, 0)
                ),
            )
        )
    return records


def export_records(
    records: Iterable[ExportRecord], out: Path, *, include_partial: bool = False
) -> list[dict[str, Any]]:
    """Write reports, exact prompts, config manifests, and an index."""
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for record in records:
        if record.partial and not include_partial:
            continue
        meta = record.metadata
        config_name = str(meta.get("config", meta.get("condition", "unknown")))
        variant = str(meta.get("data_variant", "unknown"))
        effort = str(meta.get("effort", "unknown"))
        backend = str(meta.get("backend", "unknown"))
        agent = _safe_name(meta.get("agent", "unknown"))
        scaffold = _safe_name(
            meta.get(
                "scaffold",
                {"claude": "claude-code", "codex": "codex-cli"}.get(
                    str(meta.get("agent")),
                    f"{backend}-{meta.get('agent', 'unknown')}",
                ),
            )
        )
        model = _safe_name(meta.get("model", "unknown"))
        prompt_id = hashlib.sha256(record.prompt.encode()).hexdigest()[:8]
        # Group by the actual agent loop. Native and subscription transports
        # may be pooled when they run the same Claude Code/Codex scaffold;
        # genuinely different ReAct implementations remain separate.
        group = out / f"{scaffold}_{config_name}_{variant}_{effort}_p{prompt_id}"
        group.mkdir(parents=True, exist_ok=True)
        name = (
            f"{agent}_{model}_r{record.epoch}_{_safe_name(Path(record.log_file).stem)}"
            f"_{_safe_name(record.sample_id)}{'_partial' if record.partial else ''}.md"
        )
        destination = group / name
        destination.write_text(record.report)

        config_manifest = {
            "scaffold": scaffold,
            "config": config_name,
            "prompt_id": prompt_id,
            "budget_min": meta.get("budget_min"),
            "data_variant": variant,
            "effort": effort,
        }
        config_path = group / "CONFIG.json"
        if (
            config_path.exists()
            and json.loads(config_path.read_text()) != config_manifest
        ):
            raise RuntimeError(f"inconsistent config in {group}")
        config_path.write_text(json.dumps(config_manifest, indent=2) + "\n")
        if record.prompt:
            prompts = out / "prompts"
            prompts.mkdir(exist_ok=True)
            prompt_path = prompts / f"{prompt_id}.txt"
            if not prompt_path.exists():
                prompt_path.write_text(record.prompt)

        usage = {
            key: meta.get(key)
            for key in (
                "input_tokens",
                "input_tokens_uncached",
                "output_tokens",
                "reasoning_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "cache_read_fraction",
                "cost_usd",
                "usage_schema",
                "usage_source",
            )
            if key in meta
        }
        rows.append(
            {
                "report": str(destination.relative_to(out)),
                "source": "inspect_eval_log",
                "log_file": record.log_file,
                "sample_id": record.sample_id,
                "partial": record.partial,
                "backend": backend,
                "scaffold": scaffold,
                "config": config_name,
                "prompt_id": prompt_id,
                "budget_min": meta.get("budget_min"),
                "data_variant": variant,
                "effort": effort,
                "agent": meta.get("agent"),
                "model": meta.get("model"),
                "replicate": record.epoch,
                "usage": usage or None,
            }
        )
    (out / "index.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return rows


def export_logs(
    log_dir: Path,
    out: Path,
    *,
    backend: str | None = "inspect",
    include_partial: bool = False,
) -> list[dict[str, Any]]:
    """Read ``log_dir`` through Inspect's public Log API and export reports."""
    from inspect_ai.log import list_eval_logs, read_eval_log

    records: list[ExportRecord] = []
    for info in list_eval_logs(str(log_dir), formats=["eval"]):
        log = read_eval_log(info)
        records.extend(records_from_log(log, info.name, backend=backend))
    return export_records(records, out, include_partial=include_partial)
