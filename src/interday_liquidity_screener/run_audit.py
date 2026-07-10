from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .recommendation import RecommendationPack, build_recommendation_pack


AUDITED_ARTIFACTS = [
    "stage1",
    "stage2",
    "stage3a_broker",
    "stage3b",
    "stage3c",
    "stage4",
    "hybrid_watchlist",
    "stage5_trades",
    "stage6_report",
]

RUN_AUDIT_SCHEMA_VERSION = "run-audit-v1"


@dataclass(frozen=True)
class StageArtifactAudit:
    key: str
    path: str
    exists: bool
    size_bytes: int
    row_count: int | None
    status: str


@dataclass(frozen=True)
class RunAuditReport:
    schema_version: str
    run_id: str
    overall_status: str
    summary: dict[str, Any]
    artifacts: list[StageArtifactAudit]
    missing_artifacts: list[str]
    recommendation: dict[str, Any] | None
    next_action: str
    caveat: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _artifact_audit(run_dir: Path, key: str, resolve_artifact_path) -> StageArtifactAudit:
    path = resolve_artifact_path(run_dir, key)
    exists = path.exists()
    size = path.stat().st_size if exists and path.is_file() else 0
    row_count: int | None = None
    if exists and path.suffix.lower() == ".csv" and size > 0:
        try:
            row_count = int(len(pd.read_csv(path)))
        except Exception:
            row_count = None
    if not exists:
        status = "MISSING"
    elif size == 0:
        status = "EMPTY"
    elif row_count == 0:
        status = "NO_ROWS"
    else:
        status = "OK"
    return StageArtifactAudit(
        key=key,
        path=str(path),
        exists=exists,
        size_bytes=size,
        row_count=row_count,
        status=status,
    )


def _overall_status(missing: list[str], recommendation: RecommendationPack | None) -> str:
    if "hybrid_watchlist" in missing:
        return "BLOCKED_MISSING_HYBRID_WATCHLIST"
    if recommendation is None or recommendation.primary is None:
        return "COMPLETE_NO_CAPITAL_SIZED_CANDIDATE"
    if recommendation.ready_count > 0:
        return "READY_FOR_REVIEW"
    if recommendation.draft_count > 0:
        return "NEEDS_MORNING_CONFIRMATION"
    if recommendation.watch_count > 0:
        return "WATCH_ONLY"
    return "NO_ACTIONABLE_CANDIDATE"


def _next_action(overall_status: str, run_id: str) -> str:
    if overall_status == "BLOCKED_MISSING_HYBRID_WATCHLIST":
        return "Run or resume through Stage Hybrid before asking for recommendations."
    if overall_status == "READY_FOR_REVIEW":
        return "Review the primary candidate, confirm live price/orderbook, and keep the planned entry, TP, and SL constraints intact."
    if overall_status == "NEEDS_MORNING_CONFIRMATION":
        return f"Resume run {run_id} with Fase Pagi/orderbook confirmation before any execution decision."
    if overall_status == "WATCH_ONLY":
        return "Keep the shortlist on radar; wait for a later run to upgrade status before execution planning."
    return "No execution candidate is available from this run; wait for a new scan or inspect rejected gates."


def build_run_audit_report(
    run_dir: str | Path,
    resolve_artifact_path,
    summarize_run,
    capital: float = 1_000_000.0,
    max_tp_pct: float = 0.05,
    max_position_pct: float = 1.0,
    limit: int = 5,
) -> RunAuditReport:
    root = Path(run_dir)
    if not root.exists():
        return RunAuditReport(
            schema_version=RUN_AUDIT_SCHEMA_VERSION,
            run_id=root.name,
            overall_status="MISSING_RUN",
            summary={},
            artifacts=[],
            missing_artifacts=AUDITED_ARTIFACTS.copy(),
            recommendation=None,
            next_action="The requested run directory does not exist.",
            caveat=_caveat(),
        )

    artifacts = [_artifact_audit(root, key, resolve_artifact_path) for key in AUDITED_ARTIFACTS]
    missing = [artifact.key for artifact in artifacts if artifact.status in {"MISSING", "EMPTY"}]
    summary = summarize_run(root)

    recommendation: RecommendationPack | None = None
    watchlist_path = resolve_artifact_path(root, "hybrid_watchlist")
    if watchlist_path.exists() and watchlist_path.stat().st_size > 0:
        try:
            recommendation = build_recommendation_pack(
                pd.read_csv(watchlist_path),
                run_id=root.name,
                capital=capital,
                max_tp_pct=max_tp_pct,
                max_position_pct=max_position_pct,
                limit=limit,
            )
        except Exception:
            recommendation = None

    status = _overall_status(missing, recommendation)
    return RunAuditReport(
        schema_version=RUN_AUDIT_SCHEMA_VERSION,
        run_id=root.name,
        overall_status=status,
        summary=summary,
        artifacts=artifacts,
        missing_artifacts=missing,
        recommendation=recommendation.to_dict() if recommendation else None,
        next_action=_next_action(status, root.name),
        caveat=_caveat(),
    )


def render_run_audit_markdown(report: RunAuditReport) -> str:
    lines = [
        f"# Run Audit: {report.run_id}",
        "",
        f"- **Schema**: {report.schema_version}",
        f"- **Overall status**: {report.overall_status}",
        f"- **Next action**: {report.next_action}",
    ]
    if report.summary:
        lines.extend(
            [
                f"- **Stage 1 rows**: {report.summary.get('stage1_rows', 0)}",
                f"- **Stage 2 rows**: {report.summary.get('stage2_rows', 0)}",
                f"- **Hybrid watch rows**: {report.summary.get('hybrid_watch_rows', 0)}",
                f"- **Execution ready**: {report.summary.get('hybrid_ready', 0)}",
            ]
        )
    if report.recommendation and report.recommendation.get("primary"):
        primary = report.recommendation["primary"]
        lines.extend(
            [
                "",
                "## Primary Candidate",
                f"- **Symbol**: {primary.get('symbol')}",
                f"- **Grade / Confidence**: {primary.get('decision_grade')} / {primary.get('confidence_score')}",
                f"- **Status**: {primary.get('final_status')}",
                f"- **Audit flags**: {', '.join(primary.get('audit_flags') or []) or 'CLEAR'}",
            ]
        )
    lines.extend(["", "## Artifacts", "| Artifact | Status | Rows | Size |", "|---|---|---:|---:|"])
    for artifact in report.artifacts:
        row_text = "-" if artifact.row_count is None else str(artifact.row_count)
        lines.append(f"| {artifact.key} | {artifact.status} | {row_text} | {artifact.size_bytes} |")
    lines.extend(["", f"**Caveat**: {report.caveat}"])
    return "\n".join(lines)


def _caveat() -> str:
    return "This audit checks run artifacts and decision-support readiness; it is not an order instruction."
