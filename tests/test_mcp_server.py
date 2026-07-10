from __future__ import annotations

import ast
import sys
import types
import json
from types import SimpleNamespace

import pandas as pd

from interday_liquidity_screener.constants import WatchlistStatus


class _FakeFastMCP:
    def __init__(self, name: str) -> None:
        self.name = name

    def tool(self):
        def decorator(func):
            return func

        return decorator

    def run(self) -> None:
        return None


if "mcp.server.fastmcp" not in sys.modules:
    mcp_module = types.ModuleType("mcp")
    server_module = types.ModuleType("mcp.server")
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")
    fastmcp_module.FastMCP = _FakeFastMCP
    sys.modules["mcp"] = mcp_module
    sys.modules["mcp.server"] = server_module
    sys.modules["mcp.server.fastmcp"] = fastmcp_module

from interday_liquidity_screener import mcp_server


def test_load_runtime_env_reads_dotenv_without_overriding_process_env(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        'STOCKBIT_TOKEN="stockbit-from-file"\n'
        "DEEPSEEK_API_KEY='deepseek-from-file'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("STOCKBIT_TOKEN", "stockbit-from-process")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    mcp_server._load_runtime_env(env_path)

    assert mcp_server.os.environ["STOCKBIT_TOKEN"] == "stockbit-from-process"
    assert mcp_server.os.environ["DEEPSEEK_API_KEY"] == "deepseek-from-file"


def test_get_mcp_capabilities_returns_llm_readable_json() -> None:
    result = mcp_server.get_mcp_capabilities(output_format="json")
    payload = json.loads(result)
    tools = {item["name"]: item for item in payload["capabilities"]}

    assert payload["server"] == "IDX Trading Screener"
    assert payload["server_version"] == "professional-mvp-server-v1"
    assert payload["schema_version"] == "mcp-capabilities-v1"
    assert payload["recommended_workflow"][0] == "get_mcp_capabilities"
    assert tools["run_trading_pipeline"]["mutation_level"] == "writes_run_artifacts"
    assert tools["get_trade_recommendation"]["mutation_level"] == "read_only"
    assert tools["get_execution_summary"]["category"] == "decision_support"
    assert "get_system_health" in tools
    assert "get_recommendation_policy" in tools
    assert tools["scan_bandar_activity"]["mutation_level"] == "writes_cache_artifacts"
    assert tools["get_commodity_prices"]["category"] == "market_data"
    assert tools["get_live_monitor_status"]["mutation_level"] == "read_only"


def test_mcp_capability_manifest_matches_registered_tools() -> None:
    source_path = mcp_server.Path(mcp_server.__file__)
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    registered_tools = {
        node.name
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "mcp"
            and decorator.func.attr == "tool"
            for decorator in node.decorator_list
        )
    }
    manifested_tools = {item.name for item in mcp_server.MCP_CAPABILITIES}

    assert manifested_tools == registered_tools


def test_get_mcp_capabilities_returns_markdown() -> None:
    result = mcp_server.get_mcp_capabilities()

    assert "# MCP Capabilities" in result
    assert "mcp-capabilities-v1" in result
    assert "Recommended Workflow" in result
    assert "get_trade_recommendation" in result
    assert "writes_run_artifacts" in result


def test_get_mcp_capabilities_rejects_invalid_output_format() -> None:
    result = mcp_server.get_mcp_capabilities(output_format="xml")

    assert result.startswith("Error: Invalid MCP input.")
    assert "output_format must be 'markdown' or 'json'." in result


def test_get_recommendation_policy_returns_json_manifest() -> None:
    result = mcp_server.get_recommendation_policy(output_format="json")
    payload = json.loads(result)

    assert payload["schema_version"] == "recommendation-pack-v1"
    assert payload["policy_version"] == "2026-07-professional-mvp-v1"
    assert payload["policy"]["min_risk_reward"] == 1.2
    assert "REVIEW_BUY" in payload["labels"]["execution_decisions"]
    assert "LOW_NET_PROFIT_AFTER_COSTS" in payload["labels"]["audit_flags"]
    assert "take_profit_1" in payload["column_aliases"]["tp1_price"]
    assert payload["maintainer_notes"]


def test_get_recommendation_policy_returns_markdown() -> None:
    result = mcp_server.get_recommendation_policy()

    assert "# Recommendation Policy Manifest" in result
    assert "Policy Thresholds" in result
    assert "Column Aliases" in result
    assert "RecommendationPolicy" in result


def test_get_recommendation_policy_rejects_invalid_output_format() -> None:
    result = mcp_server.get_recommendation_policy(output_format="xml")

    assert result.startswith("Error: Invalid MCP input.")
    assert "output_format must be 'markdown' or 'json'." in result


def test_get_system_health_returns_preflight_json(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("STOCKBIT_TOKEN", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    input_root = tmp_path / "input"
    run_root = tmp_path / "runs"
    config_path = tmp_path / "config" / "screener.yml"
    static_index = tmp_path / "static" / "index.html"
    preset_file = tmp_path / "lq45.txt"
    market_db = tmp_path / "market.sqlite"
    input_root.mkdir()
    run_dir = run_root / "20260708_201500"
    run_dir.mkdir(parents=True)
    (run_dir / "stage1_liquidity.csv").write_text("symbol\nBBCA\n", encoding="utf-8")
    config_path.parent.mkdir()
    config_path.write_text("risk: {}\n", encoding="utf-8")
    static_index.parent.mkdir()
    static_index.write_text("<html></html>", encoding="utf-8")
    preset_file.write_text("BBCA\nTLKM\n", encoding="utf-8")
    market_db.write_bytes(b"sqlite")

    monkeypatch.setattr(mcp_server, "DEFAULT_INPUT_ROOT", input_root)
    monkeypatch.setattr(mcp_server, "DEFAULT_RUN_ROOT", run_root)
    monkeypatch.setattr(mcp_server, "DEFAULT_MARKET_DATA_DB", market_db)
    monkeypatch.setattr(mcp_server, "DEFAULT_HYBRID_CONFIG_PATH", config_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_STATIC_INDEX_PATH", static_index)
    monkeypatch.setattr(
        mcp_server,
        "UNIVERSE_PRESETS",
        [
            SimpleNamespace(
                key="lq45",
                label="LQ45",
                description="Liquid IDX names",
                path=preset_file,
            )
        ],
    )

    result = mcp_server.get_system_health(output_format="json")
    payload = json.loads(result)

    assert payload["schema_version"] == "mcp-health-v1"
    assert payload["server_version"] == "professional-mvp-server-v1"
    assert payload["overall_status"] == "OK"
    assert payload["run_count"] == 1
    assert payload["preset_count"] == 1
    assert payload["presets"][0]["ticker_count"] == 2
    assert payload["env"]["stockbit_token_available"] is False


def test_get_system_health_reports_blocked_when_required_paths_missing(tmp_path, monkeypatch) -> None:
    preset_file = tmp_path / "missing_lq45.txt"

    monkeypatch.setattr(mcp_server, "DEFAULT_INPUT_ROOT", tmp_path / "missing_input")
    monkeypatch.setattr(mcp_server, "DEFAULT_RUN_ROOT", tmp_path / "missing_runs")
    monkeypatch.setattr(mcp_server, "DEFAULT_HYBRID_CONFIG_PATH", tmp_path / "missing_config.yml")
    monkeypatch.setattr(mcp_server, "DEFAULT_STATIC_INDEX_PATH", tmp_path / "missing_static.html")
    monkeypatch.setattr(mcp_server, "DEFAULT_MARKET_DATA_DB", tmp_path / "missing_market.sqlite")
    monkeypatch.setattr(
        mcp_server,
        "UNIVERSE_PRESETS",
        [
            SimpleNamespace(
                key="lq45",
                label="LQ45",
                description="Liquid IDX names",
                path=preset_file,
            )
        ],
    )

    result = mcp_server.get_system_health(output_format="json")
    payload = json.loads(result)

    assert payload["overall_status"] == "BLOCKED"
    assert "input_root" in {item["kind"] for item in payload["paths"] if item["status"] == "MISSING"}
    assert payload["presets"][0]["status"] == "CHECK"


def test_get_system_health_treats_dynamic_presets_as_ready(tmp_path, monkeypatch) -> None:
    input_root = tmp_path / "input"
    run_root = tmp_path / "runs"
    config_path = tmp_path / "config" / "screener.yml"
    input_root.mkdir()
    run_root.mkdir()
    config_path.parent.mkdir()
    config_path.write_text("risk: {}\n", encoding="utf-8")

    monkeypatch.setattr(mcp_server, "DEFAULT_INPUT_ROOT", input_root)
    monkeypatch.setattr(mcp_server, "DEFAULT_RUN_ROOT", run_root)
    monkeypatch.setattr(mcp_server, "DEFAULT_HYBRID_CONFIG_PATH", config_path)
    monkeypatch.setattr(mcp_server, "DEFAULT_STATIC_INDEX_PATH", tmp_path / "missing_static.html")
    monkeypatch.setattr(mcp_server, "DEFAULT_MARKET_DATA_DB", tmp_path / "missing_market.sqlite")
    monkeypatch.setattr(
        mcp_server,
        "UNIVERSE_PRESETS",
        [
            SimpleNamespace(
                key="manual",
                label="Manual / upload sendiri",
                description="Dynamic manual universe",
                path=None,
            )
        ],
    )

    result = mcp_server.get_system_health(output_format="json")
    payload = json.loads(result)

    assert payload["overall_status"] == "OK"
    assert payload["presets"][0]["status"] == "DYNAMIC"
    assert payload["next_action"] == "System preflight looks ready for MCP-driven scans."


def test_get_system_health_rejects_invalid_output_format() -> None:
    result = mcp_server.get_system_health(output_format="xml")

    assert result.startswith("Error: Invalid MCP input.")
    assert "output_format must be 'markdown' or 'json'." in result


def test_run_trading_pipeline_uses_created_run_paths(tmp_path, monkeypatch) -> None:
    input_root = tmp_path / "input"
    run_root = tmp_path / "runs"
    market_db = tmp_path / "market.sqlite"
    preset_file = tmp_path / "lq45.txt"
    preset_file.write_text("BBCA\nTLKM\n", encoding="utf-8")

    captured = {}

    def fake_run_pipeline(options, stages, paths=None, resume=False):
        captured["options"] = options
        captured["stages"] = stages
        captured["paths"] = paths
        captured["resume"] = resume
        paths.run_dir.mkdir(parents=True, exist_ok=True)
        return paths, [SimpleNamespace(ok=True, name="Stage 1")]

    monkeypatch.setattr(mcp_server, "DEFAULT_INPUT_ROOT", input_root)
    monkeypatch.setattr(mcp_server, "DEFAULT_RUN_ROOT", run_root)
    monkeypatch.setattr(mcp_server, "DEFAULT_MARKET_DATA_DB", market_db)
    monkeypatch.setattr(mcp_server, "create_run_id", lambda: "20260708_201500")
    monkeypatch.setattr(
        "interday_liquidity_screener.ticker_universe.load_universe_tickers",
        lambda key: ["BBCA.JK", "TLKM.JK"] if key == "lq45" else []
    )
    monkeypatch.setattr(mcp_server, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(
        mcp_server,
        "summarize_run",
        lambda run_dir: {
            "formatted_date": "2026-07-08 20:15:00",
            "stage1_rows": 2,
            "stage2_rows": 2,
            "valid_trade_plans": 1,
            "hybrid_ready": 1,
            "closed_trades": 0,
            "report_available": True,
        },
    )

    result = mcp_server.run_trading_pipeline(universe_key="lq45")

    assert "20260708_201500" in result
    assert captured["paths"].run_id == "20260708_201500"
    assert captured["paths"].run_dir == run_root / "20260708_201500"
    assert captured["options"].tickers_file == input_root / "mcp_tickers_20260708_201500.txt"
    assert captured["options"].tickers_file.read_text(encoding="utf-8") == "BBCA.JK\nTLKM.JK\n"
    assert captured["resume"] is False


def test_run_trading_pipeline_resume_reuses_existing_ticker_file(tmp_path, monkeypatch) -> None:
    input_root = tmp_path / "input"
    run_root = tmp_path / "runs"
    market_db = tmp_path / "market.sqlite"
    original_ticker_file = input_root / "mcp_tickers_20260708_205047.txt"
    original_ticker_file.parent.mkdir(parents=True)
    original_ticker_file.write_text("PGEO.JK\nASII.JK\n", encoding="utf-8")
    preset_file = tmp_path / "lq45.txt"
    preset_file.write_text("BBCA\nTLKM\n", encoding="utf-8")

    captured = {}

    def fake_run_pipeline(options, stages, paths=None, resume=False):
        captured["options"] = options
        captured["stages"] = stages
        captured["paths"] = paths
        captured["resume"] = resume
        paths.run_dir.mkdir(parents=True, exist_ok=True)
        return paths, [SimpleNamespace(ok=True, name="Stage 3C")]

    monkeypatch.setattr(mcp_server, "DEFAULT_INPUT_ROOT", input_root)
    monkeypatch.setattr(mcp_server, "DEFAULT_RUN_ROOT", run_root)
    monkeypatch.setattr(mcp_server, "DEFAULT_MARKET_DATA_DB", market_db)
    monkeypatch.setattr(
        mcp_server,
        "UNIVERSE_PRESETS",
        [
            SimpleNamespace(
                key="lq45",
                label="LQ45",
                description="Liquid IDX names",
                path=preset_file,
            )
        ],
    )
    monkeypatch.setattr(mcp_server, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(
        mcp_server,
        "summarize_run",
        lambda run_dir: {
            "formatted_date": "2026-07-08 20:50:47",
            "stage1_rows": 2,
            "stage2_rows": 2,
            "valid_trade_plans": 0,
            "hybrid_ready": 0,
            "closed_trades": 0,
            "report_available": True,
        },
    )

    result = mcp_server.run_trading_pipeline(
        universe_key="lq45",
        run_phase="pagi",
        resume_run_id="20260708_205047",
    )

    assert "20260708_205047" in result
    assert captured["resume"] is True
    assert captured["options"].tickers_file == original_ticker_file
    assert set(captured["options"].tickers_file.read_text(encoding="utf-8").splitlines()) == {"PGEO.JK", "ASII.JK"}
    assert captured["stages"][0] == mcp_server.PipelineStage.STAGE3C


def test_run_trading_pipeline_rejects_invalid_inputs_before_pipeline(monkeypatch) -> None:
    called = {}

    def fake_run_pipeline(*args, **kwargs):
        called["run"] = True
        raise AssertionError("run_pipeline should not be called for invalid MCP inputs")

    monkeypatch.setattr(mcp_server, "run_pipeline", fake_run_pipeline)

    result = mcp_server.run_trading_pipeline(
        strategy_mode="scalping",
        capital=0,
        risk_per_trade_pct=-0.1,
        max_position_pct=1.5,
        run_phase="besok",
    )

    assert result.startswith("Error: Invalid MCP input.")
    assert "strategy_mode must be 'interday' or 'bpjs'." in result
    assert "run_phase must be 'malam', 'pagi', or 'semua'." in result
    assert "capital must be greater than 0." in result
    assert "risk_per_trade_pct must be greater than 0 and no more than 0.10." in result
    assert "max_position_pct must be greater than 0 and no more than 1.0." in result
    assert called == {}


def test_main_runs_mcp_server(monkeypatch) -> None:
    called = {}

    monkeypatch.setattr(mcp_server.mcp, "run", lambda: called.setdefault("run", True))

    mcp_server.main()

    assert called["run"] is True


def test_get_trade_recommendation_reads_hybrid_watchlist(tmp_path, monkeypatch) -> None:
    run_root = tmp_path / "runs"
    run_dir = run_root / "20260708_205047"
    run_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "symbol": "PGEO",
                "name": "PGEO",
                "final_status": WatchlistStatus.EXECUTION_DRAFT.value,
                "final_score": 92.2,
                "entry_price": 940,
                "tp1_price": 955,
                "stop_loss_price": 930,
                "position_value": 940_000,
            }
        ]
    ).to_csv(run_dir / "hybrid_watchlist.csv", index=False)

    monkeypatch.setattr(mcp_server, "DEFAULT_RUN_ROOT", run_root)

    result = mcp_server.get_trade_recommendation("20260708_205047", capital=1_000_000, max_tp_pct=0.05)

    assert "Professional Trade Recommendation Pack" in result
    assert "**PGEO**" in result
    assert "10 lot" in result


def test_get_trade_recommendation_can_return_json(tmp_path, monkeypatch) -> None:
    run_root = tmp_path / "runs"
    run_dir = run_root / "20260708_205047"
    run_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "symbol": "PGEO",
                "name": "PGEO",
                "final_status": WatchlistStatus.EXECUTION_DRAFT.value,
                "final_score": 92.2,
                "entry_price": 940,
                "tp1_price": 955,
                "stop_loss_price": 930,
                "position_value": 940_000,
            }
        ]
    ).to_csv(run_dir / "hybrid_watchlist.csv", index=False)

    monkeypatch.setattr(mcp_server, "DEFAULT_RUN_ROOT", run_root)

    result = mcp_server.get_trade_recommendation(
        "20260708_205047",
        capital=1_000_000,
        max_tp_pct=0.05,
        max_position_pct=0.20,
        output_format="json",
    )
    payload = json.loads(result)

    assert payload["primary"]["symbol"] == "PGEO"
    assert payload["schema_version"] == "recommendation-pack-v1"
    assert payload["policy_version"] == "2026-07-professional-mvp-v1"
    assert payload["policy"]["min_expected_net_profit_idr"] == 5000.0
    assert payload["max_position_pct"] == 0.20
    assert payload["primary"]["lots"] == 2
    assert payload["primary"]["execution_decision"] == "AVOID"
    assert payload["primary"]["confidence_components"]["final_confidence"] == payload["primary"]["confidence_score"]
    assert "POSITION_REDUCED_TO_CAP" in payload["primary"]["audit_flags"]
    assert "NEEDS_LIVE_CONFIRMATION" in payload["primary"]["audit_flags"]


def test_get_trade_recommendation_rejects_invalid_agent_inputs(tmp_path, monkeypatch) -> None:
    run_root = tmp_path / "runs"
    run_dir = run_root / "20260708_205047"
    run_dir.mkdir(parents=True)
    (run_dir / "hybrid_watchlist.csv").write_text("symbol,final_status\nPGEO,EXECUTION_READY\n", encoding="utf-8")

    monkeypatch.setattr(mcp_server, "DEFAULT_RUN_ROOT", run_root)

    result = mcp_server.get_trade_recommendation(
        "20260708_205047",
        capital=-1,
        max_tp_pct=1.5,
        max_position_pct=1.5,
        limit=0,
        output_format="yaml",
    )

    assert result.startswith("Error: Invalid MCP input.")
    assert "capital must be greater than 0." in result
    assert "max_tp_pct must be greater than 0 and no more than 1.0." in result
    assert "max_position_pct must be greater than 0 and no more than 1.0." in result
    assert "limit must be an integer between 1 and 50." in result
    assert "output_format must be 'markdown' or 'json'." in result


def test_get_execution_summary_returns_compact_json(tmp_path, monkeypatch) -> None:
    run_root = tmp_path / "runs"
    run_dir = run_root / "20260708_205047"
    run_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "symbol": "PGEO",
                "final_status": WatchlistStatus.EXECUTION_DRAFT.value,
                "final_score": 92.2,
                "entry_price": 940,
                "tp1_price": 955,
                "stop_loss_price": 930,
                "position_value": 940_000,
            }
        ]
    ).to_csv(run_dir / "hybrid_watchlist.csv", index=False)

    monkeypatch.setattr(mcp_server, "DEFAULT_RUN_ROOT", run_root)

    result = mcp_server.get_execution_summary(
        "20260708_205047",
        capital=1_000_000,
        max_tp_pct=0.05,
        output_format="json",
    )
    payload = json.loads(result)

    assert payload["schema_version"] == "recommendation-pack-v1"
    assert payload["primary"]["symbol"] == "PGEO"
    assert payload["primary"]["execution_decision"] == "WAIT_CONFIRMATION"
    assert payload["portfolio_decision"] == "WITHIN_BUDGET_REVIEW"
    assert payload["data_quality"]["total_rows"] == 1


def test_get_execution_summary_returns_markdown(tmp_path, monkeypatch) -> None:
    run_root = tmp_path / "runs"
    run_dir = run_root / "20260708_205047"
    run_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "symbol": "BBCA",
                "final_status": WatchlistStatus.EXECUTION_READY.value,
                "final_score": 95,
                "entry_price": 6_175,
                "tp1_price": 6_275,
                "stop_loss_price": 6_100,
                "position_value": 617_500,
                "net_profit_after_fee": 8_000,
            }
        ]
    ).to_csv(run_dir / "hybrid_watchlist.csv", index=False)

    monkeypatch.setattr(mcp_server, "DEFAULT_RUN_ROOT", run_root)

    result = mcp_server.get_execution_summary("20260708_205047", capital=1_000_000)

    assert "# Execution Summary: 20260708_205047" in result
    assert "**Symbol**: BBCA" in result
    assert "Decision" in result


def test_get_execution_summary_rejects_invalid_output_format() -> None:
    result = mcp_server.get_execution_summary("20260708_205047", output_format="xml")

    assert result.startswith("Error: Invalid MCP input.")
    assert "output_format must be 'markdown' or 'json'." in result


def test_get_run_audit_returns_json(tmp_path, monkeypatch) -> None:
    run_root = tmp_path / "runs"
    run_dir = run_root / "20260708_205047"
    run_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "symbol": "PGEO",
                "final_status": WatchlistStatus.EXECUTION_DRAFT.value,
                "final_score": 92.2,
                "entry_price": 940,
                "tp1_price": 955,
                "stop_loss_price": 930,
                "position_value": 940_000,
            }
        ]
    ).to_csv(run_dir / "hybrid_watchlist.csv", index=False)

    monkeypatch.setattr(mcp_server, "DEFAULT_RUN_ROOT", run_root)

    result = mcp_server.get_run_audit("20260708_205047", output_format="json")
    payload = json.loads(result)

    assert payload["schema_version"] == "run-audit-v1"
    assert payload["overall_status"] == "NEEDS_MORNING_CONFIRMATION"
    assert payload["recommendation"]["primary"]["symbol"] == "PGEO"


def test_get_run_audit_rejects_invalid_output_format() -> None:
    result = mcp_server.get_run_audit("20260708_205047", output_format="xml")

    assert result.startswith("Error: Invalid MCP input.")
    assert "output_format must be 'markdown' or 'json'." in result


def test_scan_bandar_activity_tool(monkeypatch) -> None:
    from unittest.mock import MagicMock
    mock_df = pd.DataFrame([{"ticker": "ADRO.JK", "net_buy_value": 1e9, "avg_price": 2000.0}])
    mock_scan = MagicMock(return_value=mock_df)
    monkeypatch.setattr("interday_liquidity_screener.bandar_tracker.run_bandar_scan", mock_scan)
    
    res = mcp_server.scan_bandar_activity()
    assert "ADRO.JK" in res
    assert "2000" in res


def test_get_commodity_prices_tool(monkeypatch) -> None:
    mock_comm = {
        "COAL-NEWCASTLE": {"symbol": "COAL-NEWCASTLE", "name": "Newcastle Coal", "last": 130.0, "percent": -1.2}
    }
    monkeypatch.setattr("interday_liquidity_screener.commodity_gate.fetch_live_commodities", lambda **kw: mock_comm)
    
    res = mcp_server.get_commodity_prices()
    assert "Newcastle Coal" in res
    assert "-1.2" in res


def test_get_live_monitor_status_tool(tmp_path, monkeypatch) -> None:
    status_file = tmp_path / "live_monitor_status.json"
    status_file.write_text(json.dumps({"status": "active", "alerts": []}))
    monkeypatch.setattr(mcp_server, "Path", lambda p: status_file if "live_monitor_status.json" in str(p) else Path(p))
    
    res = mcp_server.get_live_monitor_status()
    assert "active" in res


def test_get_ticker_stage_details(tmp_path, monkeypatch) -> None:
    run_id = "test_run"
    run_dir = tmp_path / run_id
    run_dir.mkdir()
    
    monkeypatch.setattr(mcp_server, "DEFAULT_RUN_ROOT", tmp_path)
    
    from interday_liquidity_screener.pipeline import STAGE_FILES
    
    stage1_df = pd.DataFrame([
        {
            "ticker": "BBRI",
            "yahoo_ticker": "BBRI.JK",
            "liquidity_bucket": "HIGH_LIQUIDITY",
            "relative_activity_bucket": "NORMAL",
            "trade_candidate_bucket": "TRADE_CANDIDATE",
            "reason": "good liquidity",
            "signal_summary": "Liquid",
            "close": 4500.0,
            "avg_value_20d": 1e9,
            "volume_ratio": 1.1
        }
    ])
    stage1_df.to_csv(run_dir / STAGE_FILES["stage1"], index=False)
    
    stage2_df = pd.DataFrame([
        {
            "ticker": "BBRI",
            "yahoo_ticker": "BBRI.JK",
            "entry_setup": "PULLBACK",
            "technical_context": "BULLISH",
            "bandar_watch_eligible": True,
            "technical_reason": "support rebound",
            "signal_summary": "Bullish rebound",
            "rsi14": 55.0,
            "atr_pct": 0.02
        }
    ])
    stage2_df.to_csv(run_dir / STAGE_FILES["stage2"], index=False)
    
    stage3b_df = pd.DataFrame([
        {
            "ticker": "BBRI",
            "yahoo_ticker": "BBRI.JK",
            "bandarmology_score": 85,
            "bandarmology_signal": "ACCUMULATION",
            "bandarmology_reason": "big buyers",
            "bandarmology_summary": "Strong accumulation",
            "top_buyer_1_code": "ZP",
            "top_buyer_2_code": "YP",
            "top_buyer_3_code": "PD",
            "top_seller_1_code": "CC",
            "top_seller_2_code": "BB",
            "top_seller_3_code": "AK"
        }
    ])
    stage3b_df.to_csv(run_dir / STAGE_FILES["stage3b"], index=False)

    res_md = mcp_server.get_ticker_stage_details(run_id, "BBRI")
    assert "# Ticker Stage Details: **BBRI.JK**" in res_md
    assert "## Stage 1 - Liquidity Screen" in res_md
    assert "HIGH_LIQUIDITY" in res_md
    assert "BULLISH" in res_md
    assert "ACCUMULATION" in res_md
    assert "ZP, YP, PD" in res_md
    
    res_json = mcp_server.get_ticker_stage_details(run_id, "BBRI", output_format="json")
    payload = json.loads(res_json)
    assert payload["ticker"] == "BBRI.JK"
    assert payload["run_id"] == run_id
    assert payload["stages"]["stage1"]["liquidity_bucket"] == "HIGH_LIQUIDITY"
    assert payload["stages"]["stage2"]["entry_setup"] == "PULLBACK"
    assert payload["stages"]["stage3b"]["bandarmology_score"] == 85
    
    res_md_missing = mcp_server.get_ticker_stage_details(run_id, "TLKM")
    assert "Ticker not present in Stage 1" in res_md_missing

