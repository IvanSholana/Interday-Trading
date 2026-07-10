"""
mcp_server.py – Model Context Protocol (MCP) server for IDX Interday Trading.

Exposes the pipeline runner, run explorer, results viewer, and presets
directly to LLM agents as native tool calls. This allows an LLM agent to
fully orchestrate historical scans, live orderbook runs, backtests, and AI
report viewing autonomously in the chat.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
import math
import os
from pathlib import Path
import sys
from typing import Optional

import pandas as pd
from mcp.server.fastmcp import FastMCP

# Ensure the package root is in sys.path
package_root = Path(__file__).resolve().parents[2]
if str(package_root) not in sys.path:
    sys.path.insert(0, str(package_root))


def _load_runtime_env(path: str | Path | None = None) -> None:
    """Load local runtime settings without overriding process environment."""
    env_path = Path(path) if path is not None else package_root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        cleaned_key = key.strip()
        if cleaned_key:
            os.environ.setdefault(cleaned_key, value.strip().strip('"').strip("'"))


_load_runtime_env()


try:
    from interday_liquidity_screener.pipeline import (
        DEFAULT_INPUT_ROOT,
        DEFAULT_MARKET_DATA_DB,
        DEFAULT_RUN_ROOT,
        PipelineOptions,
        build_run_paths,
        create_run_id,
        discover_run_dirs,
        resolve_artifact_path,
        run_pipeline,
        summarize_run,
    )
    from interday_liquidity_screener.ticker_universe import UNIVERSE_PRESETS
    from interday_liquidity_screener.tickers import load_tickers, normalize_ticker
    from interday_liquidity_screener.constants import WatchlistStatus, PipelineStage
    from interday_liquidity_screener.recommendation import (
        COLUMN_ALIASES,
        DEFAULT_RECOMMENDATION_POLICY,
        AuditFlag,
        ExecutionDecision,
        PortfolioDecision,
        PortfolioFlag,
        RECOMMENDATION_SCHEMA_VERSION,
        Readiness,
        build_recommendation_pack,
        render_recommendation_markdown,
    )
    from interday_liquidity_screener.run_audit import build_run_audit_report, render_run_audit_markdown
except ImportError:
    # Direct absolute imports if packaged differently
    from src.interday_liquidity_screener.pipeline import (
        DEFAULT_INPUT_ROOT,
        DEFAULT_MARKET_DATA_DB,
        DEFAULT_RUN_ROOT,
        PipelineOptions,
        build_run_paths,
        create_run_id,
        discover_run_dirs,
        resolve_artifact_path,
        run_pipeline,
        summarize_run,
    )
    from src.interday_liquidity_screener.ticker_universe import UNIVERSE_PRESETS
    from src.interday_liquidity_screener.tickers import load_tickers, normalize_ticker
    from src.interday_liquidity_screener.constants import WatchlistStatus, PipelineStage
    from src.interday_liquidity_screener.recommendation import (
        COLUMN_ALIASES,
        DEFAULT_RECOMMENDATION_POLICY,
        AuditFlag,
        ExecutionDecision,
        PortfolioDecision,
        PortfolioFlag,
        RECOMMENDATION_SCHEMA_VERSION,
        Readiness,
        build_recommendation_pack,
        render_recommendation_markdown,
    )
    from src.interday_liquidity_screener.run_audit import build_run_audit_report, render_run_audit_markdown


mcp = FastMCP("IDX Trading Screener")

ALLOWED_OUTPUT_FORMATS = {"markdown", "json"}
ALLOWED_RUN_PHASES = {"malam", "pagi", "semua"}
ALLOWED_STRATEGY_MODES = {"interday", "bpjs"}
DEFAULT_HYBRID_CONFIG_PATH = Path("config/screener.yml")
DEFAULT_STATIC_INDEX_PATH = Path("src/interday_liquidity_screener/static/index.html")
MCP_SERVER_VERSION = "professional-mvp-server-v1"
MCP_CAPABILITY_SCHEMA_VERSION = "mcp-capabilities-v1"
MCP_HEALTH_SCHEMA_VERSION = "mcp-health-v1"


@dataclass(frozen=True)
class McpToolCapability:
    name: str
    category: str
    mutation_level: str
    when_to_use: str
    output_formats: list[str]
    safety_note: str


MCP_CAPABILITIES = [
    McpToolCapability(
        name="get_mcp_capabilities",
        category="orientation",
        mutation_level="read_only",
        when_to_use="Start here when an LLM needs to understand the available MCP tools and safe workflow order.",
        output_formats=["markdown", "json"],
        safety_note="Does not inspect market data or mutate files.",
    ),
    McpToolCapability(
        name="get_system_health",
        category="preflight",
        mutation_level="read_only",
        when_to_use="Run before scans to verify local folders, presets, config, static build, run history, and secret availability.",
        output_formats=["markdown", "json"],
        safety_note="Reports only boolean secret availability; never returns token values.",
    ),
    McpToolCapability(
        name="get_recommendation_policy",
        category="algorithm_manifest",
        mutation_level="read_only",
        when_to_use="Inspect active recommendation thresholds, decision labels, audit flags, portfolio flags, and input column aliases.",
        output_formats=["markdown", "json"],
        safety_note="Read-only algorithm documentation for LLM maintainability; does not score or mutate runs.",
    ),
    McpToolCapability(
        name="run_trading_pipeline",
        category="pipeline_execution",
        mutation_level="writes_run_artifacts",
        when_to_use="Use only when a new scan or resume run is explicitly needed.",
        output_formats=["markdown"],
        safety_note="Creates or updates run artifacts. Prefer get_system_health first, then audit/recommendation after completion.",
    ),
    McpToolCapability(
        name="run_morning_confirmation",
        category="pipeline_execution",
        mutation_level="writes_run_artifacts",
        when_to_use="Use on market morning to resume a Fase Malam run through live orderbook confirmation.",
        output_formats=["markdown"],
        safety_note="Reuses the original ticker file for the resumed run to avoid accidental universe switching.",
    ),
    McpToolCapability(
        name="get_run_audit",
        category="decision_support",
        mutation_level="read_only",
        when_to_use="Use after a run to check artifact health, readiness, missing stages, and embedded recommendation.",
        output_formats=["markdown", "json"],
        safety_note="Decision-support only; not an order instruction.",
    ),
    McpToolCapability(
        name="get_trade_recommendation",
        category="decision_support",
        mutation_level="read_only",
        when_to_use="Use after hybrid watchlist exists to get capital-aware sizing, TP cap, net-profit, and portfolio guardrails.",
        output_formats=["markdown", "json"],
        safety_note="Returns REVIEW_BUY/WAIT_CONFIRMATION/WATCH_ONLY/AVOID semantics; user must still confirm live market conditions.",
    ),
    McpToolCapability(
        name="get_execution_summary",
        category="decision_support",
        mutation_level="read_only",
        when_to_use="Use when a chat agent needs a compact user-facing answer from the recommendation pack.",
        output_formats=["markdown", "json"],
        safety_note="Summarizes existing recommendation output only; it does not create new signals or place orders.",
    ),
    McpToolCapability(
        name="get_watchlist_results",
        category="inspection",
        mutation_level="read_only",
        when_to_use="Inspect ranked hybrid watchlist rows for a completed run.",
        output_formats=["markdown"],
        safety_note="Does not apply capital-aware portfolio policy; use get_trade_recommendation for execution review.",
    ),
    McpToolCapability(
        name="get_run_details",
        category="inspection",
        mutation_level="read_only",
        when_to_use="Inspect per-stage artifact summaries and available files for a specific run.",
        output_formats=["markdown"],
        safety_note="Useful for debugging before rerunning pipeline stages.",
    ),
    McpToolCapability(
        name="list_pipeline_runs",
        category="inspection",
        mutation_level="read_only",
        when_to_use="List historical runs before selecting a run_id for audit or recommendation.",
        output_formats=["markdown"],
        safety_note="Reads run directories only.",
    ),
    McpToolCapability(
        name="get_presets_info",
        category="universe",
        mutation_level="read_only",
        when_to_use="Discover available ticker universe presets and ticker counts.",
        output_formats=["markdown"],
        safety_note="Preset counts depend on local files.",
    ),
    McpToolCapability(
        name="get_universe_tickers",
        category="universe",
        mutation_level="read_only",
        when_to_use="Inspect tickers inside one preset before running a scan.",
        output_formats=["markdown"],
        safety_note="Does not validate whether each ticker currently trades.",
    ),
    McpToolCapability(
        name="get_ai_report",
        category="reporting",
        mutation_level="read_only",
        when_to_use="Read Stage 6 markdown report for a completed run.",
        output_formats=["markdown"],
        safety_note="Report may be dry-run/mock depending on pipeline configuration.",
    ),
    McpToolCapability(
        name="scan_bandar_activity",
        category="market_data",
        mutation_level="writes_cache_artifacts",
        when_to_use="Scan configured Stockbit brokers for smart-money accumulation activity.",
        output_formats=["markdown"],
        safety_note="May fetch live Stockbit data and write the configured scan output/cache file.",
    ),
    McpToolCapability(
        name="get_commodity_prices",
        category="market_data",
        mutation_level="writes_cache_artifacts",
        when_to_use="Inspect global commodity prices and daily changes for market context.",
        output_formats=["markdown"],
        safety_note="May fetch live commodity data and update its daily cache.",
    ),
    McpToolCapability(
        name="get_live_monitor_status",
        category="monitoring",
        mutation_level="read_only",
        when_to_use="Read the most recent alerts and state produced by the live ticker monitor.",
        output_formats=["json"],
        safety_note="Reads existing monitor output only; it does not start or alter the monitor.",
    ),
    McpToolCapability(
        name="get_ticker_stage_details",
        category="inspection",
        mutation_level="read_only",
        when_to_use="Inspect the detailed results of a specific ticker across all pipeline stages of a completed run.",
        output_formats=["markdown", "json"],
        safety_note="Reads run directories only; does not mutate files.",
    ),
]


def _validation_error(errors: list[str]) -> str:
    lines = ["Error: Invalid MCP input."]
    lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines)


def _finite_float(value: float, field: str, errors: list[str]) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be a finite number.")
        return None
    if not math.isfinite(number):
        errors.append(f"{field} must be a finite number.")
        return None
    return number


def _validate_output_format(output_format: str, errors: list[str]) -> str:
    normalized = output_format.lower().strip()
    if normalized not in ALLOWED_OUTPUT_FORMATS:
        errors.append("output_format must be 'markdown' or 'json'.")
    return normalized


def _validate_recommendation_inputs(
    capital: float,
    max_tp_pct: float,
    max_position_pct: float = 1.0,
    limit: int | None = None,
    output_format: str = "markdown",
) -> tuple[float, float, float, int | None, str, str | None]:
    errors: list[str] = []
    normalized_capital = _finite_float(capital, "capital", errors)
    if normalized_capital is not None and normalized_capital <= 0:
        errors.append("capital must be greater than 0.")

    normalized_tp = _finite_float(max_tp_pct, "max_tp_pct", errors)
    if normalized_tp is not None and not (0 < normalized_tp <= 1):
        errors.append("max_tp_pct must be greater than 0 and no more than 1.0.")

    normalized_position = _finite_float(max_position_pct, "max_position_pct", errors)
    if normalized_position is not None and not (0 < normalized_position <= 1.0):
        errors.append("max_position_pct must be greater than 0 and no more than 1.0.")

    normalized_limit: int | None = None
    if limit is not None:
        try:
            normalized_limit = int(limit)
        except (TypeError, ValueError):
            errors.append("limit must be an integer between 1 and 50.")
        else:
            if not 1 <= normalized_limit <= 50:
                errors.append("limit must be an integer between 1 and 50.")

    normalized_format = _validate_output_format(output_format, errors)
    if errors:
        return 0.0, 0.0, 0.0, normalized_limit, normalized_format, _validation_error(errors)
    return normalized_capital or 0.0, normalized_tp or 0.0, normalized_position or 0.0, normalized_limit, normalized_format, None


def _validate_pipeline_inputs(
    strategy_mode: str,
    capital: float,
    risk_per_trade_pct: float,
    max_position_pct: float,
    run_phase: str,
) -> tuple[str, float, float, float, str, str | None]:
    errors: list[str] = []
    normalized_strategy = strategy_mode.lower().strip()
    normalized_phase = run_phase.lower().strip()

    if normalized_strategy not in ALLOWED_STRATEGY_MODES:
        errors.append("strategy_mode must be 'interday' or 'bpjs'.")
    if normalized_phase not in ALLOWED_RUN_PHASES:
        errors.append("run_phase must be 'malam', 'pagi', or 'semua'.")

    normalized_capital = _finite_float(capital, "capital", errors)
    if normalized_capital is not None and normalized_capital <= 0:
        errors.append("capital must be greater than 0.")

    normalized_risk = _finite_float(risk_per_trade_pct, "risk_per_trade_pct", errors)
    if normalized_risk is not None and not (0 < normalized_risk <= 0.10):
        errors.append("risk_per_trade_pct must be greater than 0 and no more than 0.10.")

    normalized_position = _finite_float(max_position_pct, "max_position_pct", errors)
    if normalized_position is not None and not (0 < normalized_position <= 1.0):
        errors.append("max_position_pct must be greater than 0 and no more than 1.0.")

    if errors:
        return normalized_strategy, 0.0, 0.0, 0.0, normalized_phase, _validation_error(errors)
    return (
        normalized_strategy,
        normalized_capital or 0.0,
        normalized_risk or 0.0,
        normalized_position or 0.0,
        normalized_phase,
        None,
    )


def _path_health(path: Path, kind: str, required: bool = True) -> dict[str, object]:
    exists = path.exists()
    size_bytes = path.stat().st_size if exists and path.is_file() else 0
    status = "OK" if exists and (path.is_dir() or size_bytes > 0) else ("MISSING" if required else "OPTIONAL_MISSING")
    return {
        "kind": kind,
        "path": str(path),
        "exists": exists,
        "size_bytes": size_bytes,
        "status": status,
        "required": required,
    }


def _preset_health() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for preset in UNIVERSE_PRESETS:
        ticker_count = 0
        error = ""
        is_dynamic = preset.path is None
        exists = bool(preset.path and preset.path.exists())
        if exists and preset.path:
            try:
                ticker_count = len(load_tickers(preset.path))
            except Exception as exc:
                error = str(exc)
        if is_dynamic:
            status = "DYNAMIC"
        elif exists and ticker_count > 0 and not error:
            status = "OK"
        else:
            status = "CHECK"
        rows.append(
            {
                "key": preset.key,
                "label": preset.label,
                "path": str(preset.path) if preset.path else "",
                "exists": exists,
                "ticker_count": ticker_count,
                "status": status,
                "error": error,
            }
        )
    return rows


def _system_health_payload() -> dict[str, object]:
    paths = [
        _path_health(DEFAULT_INPUT_ROOT, "input_root"),
        _path_health(DEFAULT_RUN_ROOT, "run_root"),
        _path_health(DEFAULT_HYBRID_CONFIG_PATH, "hybrid_config"),
        _path_health(DEFAULT_STATIC_INDEX_PATH, "frontend_static", required=False),
        _path_health(DEFAULT_MARKET_DATA_DB, "market_data_db", required=False),
    ]
    presets = _preset_health()
    run_count = 0
    try:
        run_count = len(discover_run_dirs(DEFAULT_RUN_ROOT))
    except Exception:
        run_count = 0

    missing_required = [item["kind"] for item in paths if item["required"] and item["status"] != "OK"]
    weak_presets = [item["key"] for item in presets if item["status"] == "CHECK"]
    if missing_required:
        overall_status = "BLOCKED"
    elif weak_presets:
        overall_status = "WARN"
    else:
        overall_status = "OK"

    return {
        "schema_version": MCP_HEALTH_SCHEMA_VERSION,
        "server_version": MCP_SERVER_VERSION,
        "overall_status": overall_status,
        "cwd": str(Path.cwd()),
        "python_version": sys.version.split()[0],
        "paths": paths,
        "preset_count": len(presets),
        "presets": presets,
        "run_count": run_count,
        "env": {
            "stockbit_token_available": bool(os.getenv("STOCKBIT_TOKEN")),
            "deepseek_api_key_available": bool(os.getenv("DEEPSEEK_API_KEY")),
        },
        "next_action": (
            "Create or repair required local folders/files before running the pipeline."
            if missing_required
            else (
                "Review ticker universe preset files before relying on preset scans."
                if weak_presets
                else "System preflight looks ready for MCP-driven scans."
            )
        ),
    }


def _render_system_health_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# MCP System Health",
        "",
        f"- **Schema version**: {payload['schema_version']}",
        f"- **Server version**: {payload['server_version']}",
        f"- **Overall status**: {payload['overall_status']}",
        f"- **Python**: {payload['python_version']}",
        f"- **Runs available**: {payload['run_count']}",
        f"- **Next action**: {payload['next_action']}",
        "",
        "## Paths",
        "| Kind | Status | Required | Path |",
        "|---|---|---:|---|",
    ]
    for item in payload["paths"]:
        lines.append(f"| {item['kind']} | {item['status']} | {item['required']} | {item['path']} |")

    lines.extend(["", "## Presets", "| Key | Status | Tickers | Path |", "|---|---|---:|---|"])
    for item in payload["presets"]:
        lines.append(f"| {item['key']} | {item['status']} | {item['ticker_count']} | {item['path']} |")

    env = payload["env"]
    lines.extend(
        [
            "",
            "## Environment",
            f"- **Stockbit token available**: {env['stockbit_token_available']}",
            f"- **DeepSeek API key available**: {env['deepseek_api_key_available']}",
        ]
    )
    return "\n".join(lines)


def _capabilities_payload() -> dict[str, object]:
    return {
        "server": "IDX Trading Screener",
        "server_version": MCP_SERVER_VERSION,
        "schema_version": MCP_CAPABILITY_SCHEMA_VERSION,
        "recommended_workflow": [
            "get_mcp_capabilities",
            "get_system_health",
            "get_recommendation_policy",
            "run_trading_pipeline or list_pipeline_runs",
            "get_run_audit",
            "get_trade_recommendation",
            "run_morning_confirmation when live orderbook confirmation is required",
        ],
        "capabilities": [asdict(item) for item in MCP_CAPABILITIES],
    }


def _render_capabilities_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# MCP Capabilities",
        "",
        f"- **Schema version**: {payload['schema_version']}",
        f"- **Server version**: {payload['server_version']}",
        "",
        "## Recommended Workflow",
    ]
    for index, step in enumerate(payload["recommended_workflow"], start=1):
        lines.append(f"{index}. {step}")

    lines.extend(
        [
            "",
            "## Tools",
            "| Tool | Category | Mutation | Output | When to use | Safety |",
            "|---|---|---|---|---|---|",
        ]
    )
    for item in payload["capabilities"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    item["name"],
                    item["category"],
                    item["mutation_level"],
                    ", ".join(item["output_formats"]),
                    item["when_to_use"],
                    item["safety_note"],
                ]
            )
            + " |"
        )
    return "\n".join(lines)


def _label_values(label_class: type) -> list[str]:
    return [
        value
        for name, value in vars(label_class).items()
        if name.isupper() and isinstance(value, str)
    ]


def _recommendation_policy_payload() -> dict[str, object]:
    return {
        "schema_version": RECOMMENDATION_SCHEMA_VERSION,
        "policy_version": DEFAULT_RECOMMENDATION_POLICY.version,
        "policy": DEFAULT_RECOMMENDATION_POLICY.to_dict(),
        "labels": {
            "readiness": _label_values(Readiness),
            "execution_decisions": _label_values(ExecutionDecision),
            "portfolio_decisions": _label_values(PortfolioDecision),
            "audit_flags": _label_values(AuditFlag),
            "portfolio_flags": _label_values(PortfolioFlag),
        },
        "column_aliases": {key: list(values) for key, values in COLUMN_ALIASES.items()},
        "maintainer_notes": [
            "Recommendation policy thresholds live in RecommendationPolicy.",
            "Public output labels live in Readiness, ExecutionDecision, PortfolioDecision, AuditFlag, and PortfolioFlag.",
            "CSV compatibility is controlled by COLUMN_ALIASES; add artifact column aliases there instead of scattering fallback reads.",
            "The recommendation layer is decision support only and does not create new market signals.",
        ],
    }


def _render_recommendation_policy_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# Recommendation Policy Manifest",
        "",
        f"- **Schema version**: {payload['schema_version']}",
        f"- **Policy version**: {payload['policy_version']}",
        "",
        "## Policy Thresholds",
        "| Key | Value |",
        "|---|---:|",
    ]
    for key, value in payload["policy"].items():
        lines.append(f"| {key} | {value} |")

    lines.extend(["", "## Labels"])
    for group, values in payload["labels"].items():
        lines.append(f"- **{group}**: {', '.join(values)}")

    lines.extend(["", "## Column Aliases", "| Logical field | Accepted source columns |", "|---|---|"])
    for key, values in payload["column_aliases"].items():
        lines.append(f"| {key} | {', '.join(values)} |")

    lines.extend(["", "## Maintainer Notes"])
    for note in payload["maintainer_notes"]:
        lines.append(f"- {note}")
    return "\n".join(lines)


@mcp.tool()
def get_mcp_capabilities(output_format: str = "markdown") -> str:
    """Return an LLM-readable manifest of MCP tools and safe workflow order.

    Args:
        output_format: ``markdown`` for humans or ``json`` for structured agent use.
    """
    errors: list[str] = []
    output_format = _validate_output_format(output_format, errors)
    if errors:
        return _validation_error(errors)

    payload = _capabilities_payload()
    if output_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return _render_capabilities_markdown(payload)


@mcp.tool()
def get_recommendation_policy(output_format: str = "markdown") -> str:
    """Return active recommendation policy, labels, and column aliases.

    This is the fastest MCP entrypoint for an LLM maintainer that needs to
    understand the decision layer without opening source files.

    Args:
        output_format: ``markdown`` for humans or ``json`` for structured agent use.
    """
    errors: list[str] = []
    output_format = _validate_output_format(output_format, errors)
    if errors:
        return _validation_error(errors)

    payload = _recommendation_policy_payload()
    if output_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return _render_recommendation_policy_markdown(payload)


@mcp.tool()
def get_system_health(output_format: str = "markdown") -> str:
    """Return a read-only MCP preflight health report.

    Checks local folders, config/static artifacts, ticker presets, run history,
    and whether required optional secrets are present without revealing them.

    Args:
        output_format: ``markdown`` for humans or ``json`` for structured agent use.
    """
    errors: list[str] = []
    output_format = _validate_output_format(output_format, errors)
    if errors:
        return _validation_error(errors)

    payload = _system_health_payload()
    if output_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return _render_system_health_markdown(payload)


@mcp.tool()
def get_presets_info() -> str:
    """List all available ticker universe presets (e.g. LQ45, IDX80, Syariah) and descriptions.

    Use this tool to find out what tickers lists are ready to be used as inputs for the pipeline.
    """
    lines = ["# Available Ticker Universe Presets\n"]
    for p in UNIVERSE_PRESETS:
        ticker_count = 0
        if p.path and p.path.exists():
            try:
                tickers = load_tickers(p.path)
                ticker_count = len(tickers)
            except Exception:
                pass
        lines.append(f"- **{p.key}** ({p.label}): {p.description} ({ticker_count} tickers)")
    return "\n".join(lines)


@mcp.tool()
def get_universe_tickers(universe_key: str) -> str:
    """Return the list of tickers in a specific universe preset.

    Args:
        universe_key: The preset key (e.g., 'lq45', 'idx80', 'syariah').
    """
    if universe_key == "manual":
        return "Manual mode: no preset tickers."
    preset = [p for p in UNIVERSE_PRESETS if p.key == universe_key]
    if not preset:
        return f"Error: Universe preset '{universe_key}' not found."
    p = preset[0]
    if p.path and p.path.exists():
        try:
            tickers = load_tickers(p.path)
            return f"Tickers in {p.label} ({len(tickers)}):\n" + ", ".join(tickers)
        except Exception as e:
            return f"Error reading preset file: {e}"
    return f"Preset file for '{universe_key}' does not exist on disk."


@mcp.tool()
def list_pipeline_runs() -> str:
    """Scan and list all historical and active pipeline runs on this machine.

    Shows the date, emiten count, closed trades, win rate, and report availability.
    """
    try:
        run_dirs = discover_run_dirs(DEFAULT_RUN_ROOT)
        if not run_dirs:
            return "No pipeline runs found in the output directory."

        lines = ["# Historical Pipeline Runs\n"]
        lines.append("| Run ID | Formatted Date | Stage 1 Rows | Liquid Rows | Valid Plans | Win Rate | Report? | Error? |")
        lines.append("|---|---|---|---|---|---|---|---|")

        for d in run_dirs:
            try:
                info = summarize_run(d)
                try:
                    dt = datetime.strptime(d.name, "%Y%m%d_%H%M%S")
                    formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    formatted_date = "Unknown date"

                win_rate_str = f"{info['win_rate'] * 100:.1f}%" if info.get("win_rate") is not None else "-"
                report_str = "Yes" if info.get("report_available") else "No"
                error_str = info.get("error", "-")

                lines.append(
                    f"| `{d.name}` | {formatted_date} | {info['stage1_rows']} | {info['liquid_rows']} | "
                    f"{info['valid_trade_plans']} | {win_rate_str} | {report_str} | {error_str} |"
                )
            except Exception as e:
                lines.append(f"| `{d.name}` | Error | - | - | - | - | - | {e} |")

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to scan runs: {e}"


@mcp.tool()
def get_run_details(run_id: str) -> str:
    """Return stage availability and detailed summary metrics for a specific run.

    Args:
        run_id: The run identifier (e.g. '20260706_210737').
    """
    run_dir = DEFAULT_RUN_ROOT / run_id
    if not run_dir.exists():
        return f"Error: Run directory '{run_id}' not found."

    available_stages = {}
    from interday_liquidity_screener.pipeline import STAGE_FILES
    for stage, filename in STAGE_FILES.items():
        if stage.startswith("stage3a_"):
            p = run_dir / "stockbit" / filename
        else:
            p = run_dir / filename
        available_stages[stage] = "Available" if p.exists() else "Not run"

    try:
        summary = summarize_run(run_dir)
        dt = datetime.strptime(run_id, "%Y%m%d_%H%M%S")
        formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        summary = {}
        formatted_date = "Error parsing run ID"

    lines = [f"# Run Details: {run_id}"]
    lines.append(f"- **Execution Date**: {formatted_date}")
    lines.append(f"- **Stage 1 (Liquidity Screen)**: {summary.get('stage1_rows', 0)} rows")
    lines.append(f"- **Stage 2 (Technical Screen)**: {summary.get('stage2_rows', 0)} rows")
    lines.append(f"- **Stage 4 (Actionable Plans)**: {summary.get('valid_trade_plans', 0)} plans")
    win_rate = summary.get("win_rate")
    win_rate_str = f"{win_rate * 100:.1f}%" if win_rate is not None else "-"
    lines.append(f"- **Backtest Win Rate**: {win_rate_str}")
    lines.append(f"- **AI Report Available**: {summary.get('report_available', False)}")
    if summary.get("error"):
        lines.append(f"- **Error**: {summary['error']}")

    lines.append("\n## Stage Output Files Status")
    for stage, status in available_stages.items():
        lines.append(f"- **{stage}**: {status}")

    return "\n".join(lines)


@mcp.tool()
def get_watchlist_results(
    run_id: str,
    status_filter: Optional[str] = None,
    limit: int = 20
) -> str:
    """Load, filter, and return rows from the hybrid watchlist output (hybrid_watchlist.csv) for a run.

    Provides a clean markdown summary of the screened tickers, final scores, ranks, and final statuses.

    Args:
        run_id: The run ID.
        status_filter: Optional status to filter by (e.g. 'EXECUTION_READY', 'NEED_ORDERBOOK', 'SKIP').
                       References the WatchlistStatus enum.
        limit: Max candidates to return (defaults to 20).
    """
    run_dir = DEFAULT_RUN_ROOT / run_id
    if not run_dir.exists():
        return f"Error: Run ID '{run_id}' not found."

    path = resolve_artifact_path(run_dir, "hybrid_watchlist")
    if not path.exists():
        return f"Error: Watchlist file not found for run '{run_id}'. Make sure Stage 'hybrid' was executed."

    try:
        df = pd.read_csv(path)
    except Exception as e:
        return f"Error loading CSV: {e}"

    if df.empty:
        return "The watchlist for this run is empty."

    df = df.fillna("")

    if status_filter:
        if "final_status" in df.columns:
            df = df[df["final_status"] == status_filter]
            if df.empty:
                return f"No candidates found matching status filter: '{status_filter}'"
        else:
            return "Error: 'final_status' column missing in watchlist."

    # Sort by rank or final score
    if "rank" in df.columns and not df["rank"].isna().all():
        df = df.sort_values(by="rank")
    elif "final_score" in df.columns:
        df = df.sort_values(by="final_score", ascending=False)

    df_subset = df.head(limit)

    lines = [f"# Watchlist Candidates for Run: {run_id}"]
    if status_filter:
        lines.append(f"*Filtered by Status: {status_filter}*")
    lines.append(f"Showing top {len(df_subset)} candidates:\n")

    cols = ["symbol", "name", "final_status", "final_score", "entry_price", "tp1_price", "stop_loss_price", "position_value"]
    actual_cols = [c for c in cols if c in df_subset.columns]

    # Build markdown table header
    header = "| " + " | ".join(actual_cols) + " |"
    divider = "| " + " | ".join(["---"] * len(actual_cols)) + " |"
    lines.append(header)
    lines.append(divider)

    for _, row in df_subset.iterrows():
        vals = []
        for col in actual_cols:
            val = row[col]
            if col in ["entry_price", "tp1_price", "stop_loss_price", "position_value"]:
                try:
                    vals.append(f"Rp {float(val):,.0f}" if val != "" else "-")
                except ValueError:
                    vals.append(str(val))
            elif col == "final_score":
                try:
                    vals.append(f"{float(val):.1f}" if val != "" else "-")
                except ValueError:
                    vals.append(str(val))
            else:
                vals.append(str(val))
        lines.append("| " + " | ".join(vals) + " |")

    return "\n".join(lines)


def _load_recommendation_pack(
    run_id: str,
    capital: float,
    max_tp_pct: float,
    max_position_pct: float,
    limit: int,
):
    run_dir = DEFAULT_RUN_ROOT / run_id
    if not run_dir.exists():
        return None, f"Error: Run ID '{run_id}' not found."

    path = resolve_artifact_path(run_dir, "hybrid_watchlist")
    if not path.exists():
        return None, f"Error: Watchlist file not found for run '{run_id}'. Make sure Stage 'hybrid' was executed."

    try:
        df = pd.read_csv(path)
    except Exception as e:
        return None, f"Error loading watchlist CSV: {e}"

    return (
        build_recommendation_pack(
            df,
            run_id=run_id,
            capital=capital,
            max_tp_pct=max_tp_pct,
            max_position_pct=max_position_pct,
            limit=limit,
        ),
        None,
    )


@mcp.tool()
def get_trade_recommendation(
    run_id: str,
    capital: float = 1_000_000.0,
    max_tp_pct: float = 0.05,
    max_position_pct: float = 1.0,
    limit: int = 5,
    output_format: str = "markdown",
) -> str:
    """Return a professional capital-aware trade recommendation pack for a run.

    The recommendation layer does not create new trading signals. It reads the
    hybrid watchlist, applies capital sizing, TP-cap screening, lots, estimated
    gross profit/loss, status readiness, audit flags, confidence, and next-action guidance.

    Args:
        run_id: Pipeline run ID that contains ``hybrid_watchlist.csv``.
        capital: Available capital in IDR used for position sizing context.
        max_tp_pct: Maximum acceptable TP percentage, e.g. ``0.05`` for 5%.
        max_position_pct: Maximum capital allocation for a single candidate.
        limit: Maximum shortlist rows to render.
        output_format: ``markdown`` for humans or ``json`` for structured agent use.
    """
    capital, max_tp_pct, max_position_pct, limit, output_format, validation_error = _validate_recommendation_inputs(
        capital,
        max_tp_pct,
        max_position_pct=max_position_pct,
        limit=limit,
        output_format=output_format,
    )
    if validation_error:
        return validation_error

    pack, error = _load_recommendation_pack(
        run_id=run_id,
        capital=capital,
        max_tp_pct=max_tp_pct,
        max_position_pct=max_position_pct,
        limit=limit or 5,
    )
    if error:
        return error

    if output_format == "json":
        return json.dumps(pack.to_dict(), ensure_ascii=False, indent=2)
    return render_recommendation_markdown(pack)


def _execution_summary_payload(pack) -> dict[str, object]:
    primary = pack.primary
    return {
        "run_id": pack.run_id,
        "schema_version": pack.schema_version,
        "policy_version": pack.policy_version,
        "portfolio_decision": pack.portfolio_decision,
        "portfolio_flags": pack.portfolio_flags,
        "data_quality": pack.data_quality,
        "selected_count": pack.selected_count,
        "total_selected_position_value": pack.total_selected_position_value,
        "total_selected_expected_net_profit": pack.total_selected_expected_net_profit,
        "total_selected_max_loss_amount": pack.total_selected_max_loss_amount,
        "next_action": pack.next_action,
        "primary": None
        if primary is None
        else {
            "symbol": primary.symbol,
            "execution_decision": primary.execution_decision,
            "readiness": primary.readiness,
            "decision_grade": primary.decision_grade,
            "confidence_score": primary.confidence_score,
            "entry_price": primary.entry_price,
            "tp1_price": primary.tp1_price,
            "stop_loss_price": primary.stop_loss_price,
            "lots": primary.lots,
            "position_value": primary.position_value,
            "expected_net_profit": primary.expected_net_profit,
            "max_loss_amount": primary.max_loss_amount,
            "audit_flags": primary.audit_flags,
            "next_action": primary.next_action,
        },
        "caveat": pack.caveat,
    }


def _render_execution_summary_markdown(payload: dict[str, object]) -> str:
    lines = [
        f"# Execution Summary: {payload['run_id']}",
        "",
        f"- **Portfolio decision**: {payload['portfolio_decision']}",
        f"- **Portfolio flags**: {', '.join(payload['portfolio_flags']) if payload['portfolio_flags'] else 'CLEAR'}",
        f"- **Selected count**: {payload['selected_count']}",
        f"- **Next action**: {payload['next_action']}",
        "",
    ]
    primary = payload["primary"]
    if primary is None:
        lines.append("No primary candidate is available.")
    else:
        lines.extend(
            [
                "## Primary",
                f"- **Symbol**: {primary['symbol']}",
                f"- **Decision**: {primary['execution_decision']} ({primary['readiness']}, grade {primary['decision_grade']}, confidence {primary['confidence_score']:.1f})",
                f"- **Entry / TP / SL**: {primary['entry_price']} / {primary['tp1_price']} / {primary['stop_loss_price']}",
                f"- **Lots / position**: {primary['lots']} / {primary['position_value']}",
                f"- **Expected net / max loss**: {primary['expected_net_profit']} / {primary['max_loss_amount']}",
                f"- **Audit flags**: {', '.join(primary['audit_flags']) if primary['audit_flags'] else 'CLEAR'}",
                f"- **Candidate next action**: {primary['next_action']}",
            ]
        )
    lines.extend(["", f"**Caveat**: {payload['caveat']}"])
    return "\n".join(lines)


@mcp.tool()
def get_execution_summary(
    run_id: str,
    capital: float = 1_000_000.0,
    max_tp_pct: float = 0.05,
    max_position_pct: float = 1.0,
    output_format: str = "markdown",
) -> str:
    """Return a compact user-facing execution summary from the recommendation pack.

    This tool is safer for chat agents that need a short answer because it
    exposes the primary execution decision, portfolio decision, flags, sizing,
    and next action without requiring the agent to parse the full shortlist.
    """
    capital, max_tp_pct, max_position_pct, _, output_format, validation_error = _validate_recommendation_inputs(
        capital,
        max_tp_pct,
        max_position_pct=max_position_pct,
        output_format=output_format,
    )
    if validation_error:
        return validation_error

    pack, error = _load_recommendation_pack(
        run_id=run_id,
        capital=capital,
        max_tp_pct=max_tp_pct,
        max_position_pct=max_position_pct,
        limit=5,
    )
    if error:
        return error

    payload = _execution_summary_payload(pack)
    if output_format == "json":
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return _render_execution_summary_markdown(payload)


@mcp.tool()
def get_run_audit(
    run_id: str,
    capital: float = 1_000_000.0,
    max_tp_pct: float = 0.05,
    max_position_pct: float = 1.0,
    output_format: str = "markdown",
) -> str:
    """Audit a pipeline run for artifact health and decision readiness.

    Args:
        run_id: Pipeline run ID to audit.
        capital: Capital used to derive the embedded recommendation pack.
        max_tp_pct: Maximum TP percentage accepted by the user's plan.
        max_position_pct: Maximum capital allocation for a single candidate.
        output_format: ``markdown`` for humans or ``json`` for structured agent use.
    """
    capital, max_tp_pct, max_position_pct, _, output_format, validation_error = _validate_recommendation_inputs(
        capital,
        max_tp_pct,
        max_position_pct=max_position_pct,
        output_format=output_format,
    )
    if validation_error:
        return validation_error

    run_dir = DEFAULT_RUN_ROOT / run_id
    report = build_run_audit_report(
        run_dir,
        resolve_artifact_path=resolve_artifact_path,
        summarize_run=summarize_run,
        capital=capital,
        max_tp_pct=max_tp_pct,
        max_position_pct=max_position_pct,
    )
    if output_format == "json":
        return json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    return render_run_audit_markdown(report)


@mcp.tool()
def run_morning_confirmation(
    resume_run_id: str,
    strategy_mode: str = "interday",
    capital: float = 1_000_000.0,
    risk_per_trade_pct: float = 0.005,
    max_position_pct: float = 1.0,
    enable_market_regime: bool = True,
    enable_multibar_confirm: bool = True,
    enable_adaptive_tp: bool = True,
    enable_liquidity_sizer: bool = True,
    enable_blackout: bool = True,
) -> str:
    """Resume a Fase Malam run with Fase Pagi live orderbook confirmation.

    Args:
        resume_run_id: Existing run ID from the previous evening scan.
        strategy_mode: ``interday`` or ``bpjs``.
        capital: Available simulated capital in IDR.
        risk_per_trade_pct: Allowed risk per single trade.
        max_position_pct: Max allocation per single position.
        enable_market_regime: Enable P1 Market Regime IHSG safety filter.
        enable_multibar_confirm: Enable P2 Multi-bar setup confirmation.
        enable_adaptive_tp: Enable P3 Adaptive volatility-based Take Profit.
        enable_liquidity_sizer: Enable P4 Liquidity sizer.
        enable_blackout: Enable P5 Blackout date filter.
    """
    strategy_mode, capital, risk_per_trade_pct, max_position_pct, _, validation_error = _validate_pipeline_inputs(
        strategy_mode,
        capital,
        risk_per_trade_pct,
        max_position_pct,
        "pagi",
    )
    if validation_error:
        return validation_error

    return run_trading_pipeline(
        tickers=None,
        universe_key="lq45",
        strategy_mode=strategy_mode,
        capital=capital,
        risk_per_trade_pct=risk_per_trade_pct,
        max_position_pct=max_position_pct,
        run_phase="pagi",
        resume_run_id=resume_run_id,
        enable_market_regime=enable_market_regime,
        enable_multibar_confirm=enable_multibar_confirm,
        enable_adaptive_tp=enable_adaptive_tp,
        enable_liquidity_sizer=enable_liquidity_sizer,
        enable_blackout=enable_blackout,
    )


@mcp.tool()
def get_ai_report(run_id: str) -> str:
    """Load and return the full markdown text of the Stage 6 LLM analyst report for a run.

    Provides the investment thesis, evidence summary, and ranking narrative.

    Args:
        run_id: The run ID.
    """
    run_dir = DEFAULT_RUN_ROOT / run_id
    if not run_dir.exists():
        return f"Error: Run directory '{run_id}' not found."

    path = resolve_artifact_path(run_dir, "stage6_report")
    if not path.exists():
        return f"Error: AI report not found for run '{run_id}'. Check if Stage 6 was executed."

    try:
        content = path.read_text(encoding="utf-8")
        return content
    except Exception as e:
        return f"Error reading report: {e}"


def _existing_resume_ticker_file(run_id: str) -> Path | None:
    candidates = [
        DEFAULT_INPUT_ROOT / f"mcp_tickers_{run_id}.txt",
        DEFAULT_INPUT_ROOT / f"ui_tickers_{run_id}.txt",
        build_run_paths(DEFAULT_RUN_ROOT, run_id).ticker_input,
    ]
    for path in candidates:
        if path.exists() and path.stat().st_size > 0:
            return path
    return None


def _resolve_mcp_tickers(tickers: Optional[str], universe_key: str, resume_run_id: Optional[str]) -> list[str]:
    if tickers:
        custom = [normalize_ticker(t.strip()) for t in tickers.replace(",", "\n").splitlines() if t.strip()]
        return [t for t in custom if t]

    if resume_run_id:
        existing_file = _existing_resume_ticker_file(resume_run_id)
        if existing_file:
            return load_tickers(existing_file)

    from interday_liquidity_screener.ticker_universe import load_universe_tickers
    return load_universe_tickers(universe_key)


@mcp.tool()
def run_trading_pipeline(
    tickers: Optional[str] = None,
    universe_key: str = "lq45",
    strategy_mode: str = "interday",
    capital: float = 1_000_000.0,
    risk_per_trade_pct: float = 0.005,
    max_position_pct: float = 0.20,
    run_phase: str = "malam",
    resume_run_id: Optional[str] = None,
    enable_market_regime: bool = False,
    enable_multibar_confirm: bool = False,
    enable_adaptive_tp: bool = False,
    enable_liquidity_sizer: bool = False,
    enable_blackout: bool = False,
) -> str:
    """Run the Interday Trading screening and backtesting pipeline.

    Calculates liquidity, technical setups, bandarmology accumulation, trade plans, and final scores.

    Args:
        tickers: Commas or newlines separated list of custom tickers (e.g. 'BBRI,TLKM,BBCA'). If specified, universe_key is ignored.
        universe_key: Preset universe key if tickers is empty (e.g. 'lq45', 'idx80').
        strategy_mode: 'interday' (normal swing) or 'bpjs' (beli pagi jual siang).
        capital: Available simulated capital in IDR (defaults to 1,000,000).
        risk_per_trade_pct: Allowed risk per single trade (e.g. 0.005 = 0.5% risk).
        max_position_pct: Max allowed allocation per single position (e.g. 0.20 = 20%).
        run_phase: 'malam' (Fase 1: skips orderbook) or 'pagi' (Fase 2: includes orderbook) or 'semua' (runs all stages 1-6).
        resume_run_id: Optional run ID of a failed/previous run to resume from. Skips already executed stages.
        enable_market_regime: Enable P1 Market Regime IHSG safety filter.
        enable_multibar_confirm: Enable P2 Multi-bar setup confirmation.
        enable_adaptive_tp: Enable P3 Adaptive volatility-based Take Profit.
        enable_liquidity_sizer: Enable P4 Liquidity sizer (reduces allocation on lower volume).
        enable_blackout: Enable P5 Blackout date filter (skips ex-date/warning notations).
    """
    strategy_mode, capital, risk_per_trade_pct, max_position_pct, run_phase, validation_error = _validate_pipeline_inputs(
        strategy_mode,
        capital,
        risk_per_trade_pct,
        max_position_pct,
        run_phase,
    )
    if validation_error:
        return validation_error

    run_id = resume_run_id if resume_run_id else create_run_id()
    run_paths = build_run_paths(DEFAULT_RUN_ROOT, run_id)

    # 1. Tentukan stage berdasarkan fase
    if run_phase == "malam":
        # Fase Malam H-1 skips orderbook (stage 3c)
        stages = [
            PipelineStage.STAGE1,
            PipelineStage.STAGE2,
            PipelineStage.STAGE3A,
            PipelineStage.STAGE3B,
            PipelineStage.STAGE4,
            PipelineStage.HYBRID,
            PipelineStage.STAGE5,
            PipelineStage.STAGE6,
        ]
    elif run_phase == "pagi":
        # Fase Pagi Hari H runs live confirmation
        stages = [
            PipelineStage.STAGE3C,
            PipelineStage.STAGE4,
            PipelineStage.HYBRID,
            PipelineStage.STAGE5,
            PipelineStage.STAGE6,
        ]
    else:
        # Semua stage
        stages = [
            PipelineStage.STAGE1,
            PipelineStage.STAGE2,
            PipelineStage.STAGE3A,
            PipelineStage.STAGE3B,
            PipelineStage.STAGE3C,
            PipelineStage.STAGE4,
            PipelineStage.HYBRID,
            PipelineStage.STAGE5,
            PipelineStage.STAGE6,
        ]

    # 2. Ambil list emiten. Resume runs reuse their original MCP/UI ticker file
    # so morning confirmation does not accidentally switch universe presets.
    tickers_list = _resolve_mcp_tickers(tickers, universe_key, resume_run_id)

    if not tickers_list:
        return "Error: Ticker list is empty. Provide custom tickers or select a valid universe preset."

    ticker_file_path = DEFAULT_INPUT_ROOT / f"mcp_tickers_{run_id}.txt"
    ticker_file_path.parent.mkdir(parents=True, exist_ok=True)
    ticker_file_path.write_text("\n".join(tickers_list) + "\n", encoding="utf-8")

    # 3. Bangun PipelineOptions
    options = PipelineOptions(
        tickers_file=ticker_file_path,
        run_root=DEFAULT_RUN_ROOT,
        market_data_db=DEFAULT_MARKET_DATA_DB,
        run_date=date.today().isoformat(),
        period_stage1="3mo",
        period_stage2="1y",
        windows="1D,3D,5D,10D,20D",
        strategy_mode=strategy_mode,
        capital=capital,
        risk_per_trade_pct=risk_per_trade_pct,
        max_position_pct=max_position_pct,
        bandarmology_min_score=60,
        dry_run_llm=True,  # LLM report generated locally in mock/dry mode
        refresh_market_data=False,
        allow_trade_without_broker_data=False,
        require_orderbook_confirmation=True if strategy_mode == "bpjs" else None,
        strict_corporate_action_filter=False,
        hybrid_mode="bpjs_live" if strategy_mode == "bpjs" else "normal_execution",
        hybrid_capital_profile="capital_500k" if capital <= 750000 else ("capital_1m" if capital <= 1250000 else "capital_1_5m"),
        hybrid_config_path=Path("config/screener.yml"),
        hybrid_max_candidates=30,
        enable_market_regime=enable_market_regime,
        enable_multibar_confirm=enable_multibar_confirm,
        enable_adaptive_tp=enable_adaptive_tp,
        enable_liquidity_sizer=enable_liquidity_sizer,
        enable_blackout=enable_blackout,
    )

    try:
        # Run pipeline synchronously for the MCP tool call
        paths, results = run_pipeline(options, stages, paths=run_paths, resume=bool(resume_run_id))
        failed_stages = [r.name for r in results if not r.ok]

        if failed_stages:
            return (
                f"Pipeline run '{run_id}' completed with failures.\n"
                f"- **Succeeded**: {len(results) - len(failed_stages)} stages\n"
                f"- **Failed**: {', '.join(failed_stages)}\n"
                f"You can use get_run_details('{run_id}') to view logs."
            )

        summary = summarize_run(paths.run_dir)
        return (
            f"Successfully executed pipeline! Run ID: **{run_id}**\n\n"
            f"### Run Summary:\n"
            f"- **Date**: {summary.get('formatted_date', run_id)}\n"
            f"- **Stage 1 (Liquidity)**: {summary.get('stage1_rows', 0)} rows\n"
            f"- **Stage 2 (Technical)**: {summary.get('stage2_rows', 0)} rows\n"
            f"- **Stage 4 (Actionable Trade Plans)**: {summary.get('valid_trade_plans', 0)} plans\n"
            f"- **Stage Hybrid (Execution Ready)**: {summary.get('hybrid_ready', 0)} candidates\n"
            f"- **Backtest closed trades**: {summary.get('closed_trades', 0)}\n"
            f"- **AI Report**: {'Generated' if summary.get('report_available') else 'Not generated'}\n\n"
            f"To view the watchlist candidates, call: `get_watchlist_results('{run_id}')`\n"
            f"To get a capital-aware plan, call: `get_trade_recommendation('{run_id}', capital={capital:.0f}, max_tp_pct=0.05)`"
        )
    except Exception as e:
        return f"Error executing pipeline: {e}"



def _df_to_markdown_manual(df) -> str:
    if df.empty:
        return ""
    headers = list(df.columns)
    lines = []
    lines.append("| " + " | ".join(str(h) for h in headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row[h]) for h in headers) + " |")
    return "\n".join(lines)


@mcp.tool()
def scan_bandar_activity(
    config_path: str = "config/bandar_tracker.json",
    output_path: str = "data/output/bandar_scan_results.csv",
    force_refresh: bool = False,
    investor_type: str | None = None,
    period: str | None = None
) -> str:
    """Scan and track smart money (bandar) accumulation flow for target brokers on Stockbit.
    
    Args:
        config_path: Path to tracker JSON config.
        output_path: Path to write results CSV.
        force_refresh: Set to True to bypass daily cache and force live fetch.
        investor_type: Optional override (e.g. 'INVESTOR_TYPE_FOREIGN', 'INVESTOR_TYPE_DOMESTIC').
        period: Optional override (e.g. 'RT_PERIOD_LAST_7_DAYS', 'RT_PERIOD_LAST_3_DAYS').
    """
    from interday_liquidity_screener.bandar_tracker import run_bandar_scan
    try:
        df = run_bandar_scan(
            config_path=config_path,
            output_path=output_path,
            force_refresh=force_refresh,
            override_investor_type=investor_type,
            override_period=period
        )
        if df.empty:
            return "No accumulated tickers found or error occurred."
            
        return _df_to_markdown_manual(df)
    except Exception as e:
        return f"Error running bandar scan: {e}"


@mcp.tool()
def get_commodity_prices(force_refresh: bool = False) -> str:
    """Return live global commodities prices and daily changes as a Markdown table.
    
    Args:
        force_refresh: Set to True to bypass daily cache and force live fetch.
    """
    from interday_liquidity_screener.commodity_gate import fetch_live_commodities
    import pandas as pd
    try:
        commodities = fetch_live_commodities(force_refresh=force_refresh)
        if not commodities:
            return "No commodity data retrieved."
        df = pd.DataFrame(list(commodities.values()))
        return _df_to_markdown_manual(df)
    except Exception as e:
        return f"Error retrieving commodity prices: {e}"

@mcp.tool()
def get_ticker_stage_details(
    run_id: str,
    ticker: str,
    output_format: str = "markdown"
) -> str:
    """Return the detailed metrics and status of a specific ticker across all executed pipeline stages.

    Allows auditing exactly why a ticker was screened out or selected at each step.

    Args:
        run_id: The run identifier (e.g. '20260706_210737').
        ticker: The ticker symbol (e.g. 'BBRI', 'TLKM', 'BBCA.JK').
        output_format: ``markdown`` for humans or ``json`` for structured agent use.
    """
    errors: list[str] = []
    output_format = _validate_output_format(output_format, errors)
    if errors:
        return _validation_error(errors)

    run_dir = DEFAULT_RUN_ROOT / run_id
    if not run_dir.exists():
        return f"Error: Run directory '{run_id}' not found."

    # Try normalizing the target ticker
    try:
        norm_target = normalize_ticker(ticker)
    except ValueError:
        # Fallback to uppercase clean input if normalize_ticker fails
        norm_target = ticker.strip().upper()
        if norm_target.endswith(".JK"):
            base_target = norm_target[:-3]
        else:
            base_target = norm_target
            norm_target = f"{base_target}.JK"

    if norm_target is None:
        return f"Error: Invalid ticker '{ticker}'."

    base_target = norm_target[:-3] if norm_target.endswith(".JK") else norm_target

    def match_ticker_in_df(df: pd.DataFrame) -> pd.Series | None:
        if df.empty:
            return None
        # Columns to check for matching symbols
        ticker_cols = [col for col in ["ticker", "yahoo_ticker", "symbol"] if col in df.columns]
        if not ticker_cols:
            ticker_cols = [df.columns[0]]  # Fallback to the first column

        for col in ticker_cols:
            for idx, val in df[col].items():
                if not isinstance(val, str) or not val:
                    continue
                val_upper = val.strip().upper()
                # Direct match
                if val_upper == norm_target or val_upper == base_target:
                    return df.iloc[idx]
                # Normalized match
                try:
                    norm_val = normalize_ticker(val)
                    if norm_val == norm_target:
                        return df.iloc[idx]
                except ValueError:
                    pass
        return None

    stages_data = {}
    from interday_liquidity_screener.pipeline import STAGE_FILES

    # 1. Stage 1 - Liquidity
    stage1_path = run_dir / STAGE_FILES["stage1"]
    if stage1_path.exists():
        try:
            df1 = pd.read_csv(stage1_path)
            row = match_ticker_in_df(df1)
            if row is not None:
                row = row.fillna("-")
                stages_data["stage1"] = {
                    "status": "COMPLETED",
                    "found": True,
                    "liquidity_bucket": row.get("liquidity_bucket", "-"),
                    "relative_activity_bucket": row.get("relative_activity_bucket", "-"),
                    "trade_candidate_bucket": row.get("trade_candidate_bucket", "-"),
                    "reason": row.get("reason", "-"),
                    "signal_summary": row.get("signal_summary", "-"),
                    "close": row.get("close", "-"),
                    "avg_value_20d": row.get("avg_value_20d", "-"),
                    "volume_ratio": row.get("volume_ratio", "-"),
                }
            else:
                stages_data["stage1"] = {"status": "COMPLETED", "found": False, "reason": "Ticker not present in Stage 1 input/output universe."}
        except Exception as e:
            stages_data["stage1"] = {"status": "ERROR", "error": str(e)}
    else:
        stages_data["stage1"] = {"status": "NOT_RUN"}

    # 2. Stage 2 - Technical Context
    stage2_path = run_dir / STAGE_FILES["stage2"]
    if stage2_path.exists():
        try:
            df2 = pd.read_csv(stage2_path)
            row = match_ticker_in_df(df2)
            if row is not None:
                row = row.fillna("-")
                stages_data["stage2"] = {
                    "status": "COMPLETED",
                    "found": True,
                    "entry_setup": row.get("entry_setup", "-"),
                    "technical_context": row.get("technical_context", "-"),
                    "bandar_watch_eligible": row.get("bandar_watch_eligible", "-"),
                    "technical_reason": row.get("technical_reason", "-"),
                    "signal_summary": row.get("signal_summary", "-"),
                    "rsi14": row.get("rsi14", "-"),
                    "atr_pct": row.get("atr_pct", "-"),
                }
            else:
                stages_data["stage2"] = {"status": "COMPLETED", "found": False, "reason": "Filtered out at Stage 1 (liquidity filters) or missing from Stage 2 input."}
        except Exception as e:
            stages_data["stage2"] = {"status": "ERROR", "error": str(e)}
    else:
        stages_data["stage2"] = {"status": "NOT_RUN"}

    # 3. Stage 3b - Bandarmology
    stage3b_path = run_dir / STAGE_FILES["stage3b"]
    if stage3b_path.exists():
        try:
            df3b = pd.read_csv(stage3b_path)
            row = match_ticker_in_df(df3b)
            if row is not None:
                row = row.fillna("-")
                stages_data["stage3b"] = {
                    "status": "COMPLETED",
                    "found": True,
                    "bandarmology_score": row.get("bandarmology_score", "-"),
                    "bandarmology_signal": row.get("bandarmology_signal", "-"),
                    "bandarmology_reason": row.get("bandarmology_reason", "-"),
                    "bandarmology_summary": row.get("bandarmology_summary", "-"),
                    "top_buyers": f"{row.get('top_buyer_1_code', '-')}, {row.get('top_buyer_2_code', '-')}, {row.get('top_buyer_3_code', '-')}",
                    "top_sellers": f"{row.get('top_seller_1_code', '-')}, {row.get('top_seller_2_code', '-')}, {row.get('top_seller_3_code', '-')}",
                }
            else:
                stages_data["stage3b"] = {"status": "COMPLETED", "found": False, "reason": "Filtered out before Bandarmology stage (did not pass technical/liquidity watch eligibility)."}
        except Exception as e:
            stages_data["stage3b"] = {"status": "ERROR", "error": str(e)}
    else:
        stages_data["stage3b"] = {"status": "NOT_RUN"}

    # 4. Stage 3c - Orderbook Filter
    stage3c_path = run_dir / STAGE_FILES["stage3c"]
    if stage3c_path.exists():
        try:
            df3c = pd.read_csv(stage3c_path)
            row = match_ticker_in_df(df3c)
            if row is not None:
                row = row.fillna("-")
                stages_data["stage3c"] = {
                    "status": "COMPLETED",
                    "found": True,
                    "orderbook_status": row.get("orderbook_status", "-"),
                    "orderbook_score": row.get("orderbook_score", "-"),
                    "orderbook_reason": row.get("orderbook_reason", "-"),
                    "orderbook_summary": row.get("orderbook_summary", "-"),
                    "mid_price": row.get("mid_price", "-"),
                    "spread_pct": row.get("spread_pct", "-"),
                }
            else:
                stages_data["stage3c"] = {"status": "COMPLETED", "found": False, "reason": "Filtered out or skipped for live orderbook verification."}
        except Exception as e:
            stages_data["stage3c"] = {"status": "ERROR", "error": str(e)}
    else:
        stages_data["stage3c"] = {"status": "NOT_RUN"}

    # 5. Stage 4 - Trade Plan
    stage4_path = run_dir / STAGE_FILES["stage4"]
    if stage4_path.exists():
        try:
            df4 = pd.read_csv(stage4_path)
            row = match_ticker_in_df(df4)
            if row is not None:
                row = row.fillna("-")
                stages_data["stage4"] = {
                    "status": "COMPLETED",
                    "found": True,
                    "trade_status": row.get("trade_status", "-"),
                    "is_plan_valid": row.get("is_plan_valid", "-"),
                    "trade_reason": row.get("trade_reason", "-"),
                    "trade_summary": row.get("trade_summary", "-"),
                    "entry_price": row.get("entry_price", "-"),
                    "take_profit_1": row.get("take_profit_1", "-"),
                    "stop_loss": row.get("stop_loss", "-"),
                    "position_size_lots": row.get("position_size_lots", "-"),
                    "executable_position_value": row.get("executable_position_value", "-"),
                }
            else:
                stages_data["stage4"] = {"status": "COMPLETED", "found": False, "reason": "No trade plan generated. Filtered out in previous stage."}
        except Exception as e:
            stages_data["stage4"] = {"status": "ERROR", "error": str(e)}
    else:
        stages_data["stage4"] = {"status": "NOT_RUN"}

    # 6. Hybrid Watchlist
    hybrid_path = run_dir / STAGE_FILES["hybrid_watchlist"]
    if hybrid_path.exists():
        try:
            df_h = pd.read_csv(hybrid_path)
            row = match_ticker_in_df(df_h)
            if row is not None:
                row = row.fillna("-")
                stages_data["hybrid"] = {
                    "status": "COMPLETED",
                    "found": True,
                    "final_status": row.get("final_status", "-"),
                    "final_score": row.get("final_score", "-"),
                    "rank": row.get("rank", "-"),
                    "entry_price": row.get("entry_price", "-"),
                    "tp1_price": row.get("tp1_price", "-"),
                    "stop_loss_price": row.get("stop_loss_price", "-"),
                    "position_value": row.get("position_value", "-"),
                }
            else:
                stages_data["hybrid"] = {"status": "COMPLETED", "found": False, "reason": "Not selected for the final hybrid watchlist."}
        except Exception as e:
            stages_data["hybrid"] = {"status": "ERROR", "error": str(e)}
    else:
        stages_data["hybrid"] = {"status": "NOT_RUN"}

    # Ensure all values in stages_data are native JSON-serializable types
    def clean_val(v):
        if hasattr(v, "item"):
            try:
                return v.item()
            except Exception:
                pass
        if isinstance(v, (bool, int, float, str)):
            if isinstance(v, float) and not math.isfinite(v):
                return "-"
            return v
        return str(v)

    serializable_stages = {}
    for stage_name, stage_info in stages_data.items():
        serializable_stages[stage_name] = {k: clean_val(v) for k, v in stage_info.items()}
    stages_data = serializable_stages

    if output_format == "json":
        return json.dumps({"ticker": norm_target, "run_id": run_id, "stages": stages_data}, ensure_ascii=False, indent=2)

    # Render Markdown output
    lines = [
        f"# Ticker Stage Details: **{norm_target}**",
        f"- **Run ID**: `{run_id}`",
        "",
    ]

    # Render Stage 1
    lines.append("## Stage 1 - Liquidity Screen")
    st1 = stages_data.get("stage1", {"status": "NOT_RUN"})
    if st1["status"] == "COMPLETED":
        if st1["found"]:
            lines.extend([
                f"- **Liquidity Bucket**: `{st1['liquidity_bucket']}`",
                f"- **Relative Activity**: `{st1['relative_activity_bucket']}`",
                f"- **Candidate Bucket**: `{st1['trade_candidate_bucket']}`",
                f"- **Close / Avg Value 20d / Vol Ratio**: Rp {st1['close']} / Rp {st1['avg_value_20d']} / {st1['volume_ratio']}",
                f"- **Reason**: {st1['reason']}",
                f"- **Summary**: *{st1['signal_summary']}*",
            ])
        else:
            lines.append(f"- *Filtered Out*: {st1['reason']}")
    elif st1["status"] == "ERROR":
        lines.append(f"- **Error loading Stage 1**: {st1['error']}")
    else:
        lines.append("- *Stage 1 was not run or output is missing.*")
    lines.append("")

    # Render Stage 2
    lines.append("## Stage 2 - Technical Context")
    st2 = stages_data.get("stage2", {"status": "NOT_RUN"})
    if st2["status"] == "COMPLETED":
        if st2["found"]:
            lines.extend([
                f"- **Entry Setup**: `{st2['entry_setup']}`",
                f"- **Technical Context**: `{st2['technical_context']}`",
                f"- **Bandar Watch Eligible**: `{st2['bandar_watch_eligible']}`",
                f"- **RSI (14) / ATR %**: {st2['rsi14']} / {st2['atr_pct']}",
                f"- **Reason**: {st2['technical_reason']}",
                f"- **Summary**: *{st2['signal_summary']}*",
            ])
        else:
            lines.append(f"- *Filtered Out*: {st2['reason']}")
    elif st2["status"] == "ERROR":
        lines.append(f"- **Error loading Stage 2**: {st2['error']}")
    else:
        lines.append("- *Stage 2 was not run or output is missing.*")
    lines.append("")

    # Render Stage 3b
    lines.append("## Stage 3b - Bandarmology Score")
    st3b = stages_data.get("stage3b", {"status": "NOT_RUN"})
    if st3b["status"] == "COMPLETED":
        if st3b["found"]:
            lines.extend([
                f"- **Score**: `{st3b['bandarmology_score']}`",
                f"- **Signal**: `{st3b['bandarmology_signal']}`",
                f"- **Top Buyers**: `{st3b['top_buyers']}`",
                f"- **Top Sellers**: `{st3b['top_sellers']}`",
                f"- **Reason**: {st3b['bandarmology_reason']}",
                f"- **Summary**: *{st3b['bandarmology_summary']}*",
            ])
        else:
            lines.append(f"- *Filtered Out*: {st3b['reason']}")
    elif st3b["status"] == "ERROR":
        lines.append(f"- **Error loading Stage 3b**: {st3b['error']}")
    else:
        lines.append("- *Stage 3b was not run or output is missing.*")
    lines.append("")

    # Render Stage 3c
    lines.append("## Stage 3c - Orderbook Confirmation")
    st3c = stages_data.get("stage3c", {"status": "NOT_RUN"})
    if st3c["status"] == "COMPLETED":
        if st3c["found"]:
            lines.extend([
                f"- **Status**: `{st3c['orderbook_status']}`",
                f"- **Score**: `{st3c['orderbook_score']}`",
                f"- **Mid Price**: Rp {st3c['mid_price']}",
                f"- **Spread %**: {st3c['spread_pct']}",
                f"- **Reason**: {st3c['orderbook_reason']}",
                f"- **Summary**: *{st3c['orderbook_summary']}*",
            ])
        else:
            lines.append(f"- *Filtered Out*: {st3c['reason']}")
    elif st3c["status"] == "ERROR":
        lines.append(f"- **Error loading Stage 3c**: {st3c['error']}")
    else:
        lines.append("- *Stage 3c was not run or output is missing.*")
    lines.append("")

    # Render Stage 4
    lines.append("## Stage 4 - Trade Plan")
    st4 = stages_data.get("stage4", {"status": "NOT_RUN"})
    if st4["status"] == "COMPLETED":
        if st4["found"]:
            lines.extend([
                f"- **Trade Plan Status**: `{st4['trade_status']}`",
                f"- **Plan Valid?**: `{st4['is_plan_valid']}`",
                f"- **Entry / TP1 / SL**: Rp {st4['entry_price']} / Rp {st4['take_profit_1']} / Rp {st4['stop_loss']}",
                f"- **Sizing**: {st4['position_size_lots']} lots (Value: Rp {st4['executable_position_value']})",
                f"- **Reason**: {st4['trade_reason']}",
                f"- **Summary**: *{st4['trade_summary']}*",
            ])
        else:
            lines.append(f"- *Filtered Out*: {st4['reason']}")
    elif st4["status"] == "ERROR":
        lines.append(f"- **Error loading Stage 4**: {st4['error']}")
    else:
        lines.append("- *Stage 4 was not run or output is missing.*")
    lines.append("")

    # Render Hybrid Watchlist
    lines.append("## Stage Hybrid - Final Watchlist Selection")
    sth = stages_data.get("hybrid", {"status": "NOT_RUN"})
    if sth["status"] == "COMPLETED":
        if sth["found"]:
            lines.extend([
                f"- **Final Watchlist Status**: `{sth['final_status']}`",
                f"- **Final Score**: `{sth['final_score']}`",
                f"- **Rank**: {sth['rank']}",
                f"- **Entry / TP1 / SL**: Rp {sth['entry_price']} / Rp {sth['tp1_price']} / Rp {sth['stop_loss_price']}",
                f"- **Sizing**: Rp {sth['position_value']}",
            ])
        else:
            lines.append(f"- *Filtered Out*: {sth['reason']}")
    elif sth["status"] == "ERROR":
        lines.append(f"- **Error loading Hybrid Watchlist**: {sth['error']}")
    else:
        lines.append("- *Hybrid Watchlist stage was not run or output is missing.*")
    lines.append("")

    return "\n".join(lines)


@mcp.tool()
def get_live_monitor_status() -> str:
    """Read the latest alerts and status from the live ticker monitor."""
    status_path = Path("data/output/live_monitor_status.json")
    if not status_path.exists():
        return "Live ticker monitor has not generated any status output yet."
    try:
        content = status_path.read_text(encoding="utf-8")
        parsed = json.loads(content)
        return json.dumps(parsed, indent=2)
    except Exception as e:
        return f"Error reading live monitor status: {e}"


def main() -> None:
    """Launch the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
