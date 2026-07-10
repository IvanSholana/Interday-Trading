from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import date, datetime
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any, Callable

import pandas as pd

try:
    from .backtest_interday import InterdayBacktestConfig, run_stage5_backtest_interday
    from .bandarmology import run_stage3b_bandarmology_scoring
    from .classifier import GOOD_LIQUIDITY, HIGH_LIQUIDITY
    from .config import ScreenerConfig
    from .downloader import download_ticker_data
    from .hybrid_screener import build_hybrid_watchlist, load_hybrid_config, run_hybrid_screener
    from .llm_analyst import run_llm_report, run_stage6_build_evidence
    from .metrics import compute_metrics
    from .orderbook_filter import OrderbookFilterConfig, run_stage3c_orderbook_filter
    from .paper_bpjs import BpjsPaperConfig, run_stage5_paper_bpjs
    from .reporting import build_result_frame, save_csv
    from .stockbit_collector import (
        StockbitCollectorConfig,
        parse_windows_arg,
        run_stage3a_broker_collector_multi_window,
    )
    from .technical import run_stage_2_technical_screening
    from .ticker_universe import UNIVERSE_PRESETS, get_universe_preset, read_universe_text
    from .tickers import load_tickers, normalize_ticker
    from .trade_plan import TradePlanConfig, run_stage_4_trade_plan
    from .constants import PipelineStage, WatchlistStatus
except ImportError:
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    from interday_liquidity_screener.backtest_interday import InterdayBacktestConfig, run_stage5_backtest_interday
    from interday_liquidity_screener.bandarmology import run_stage3b_bandarmology_scoring
    from interday_liquidity_screener.classifier import GOOD_LIQUIDITY, HIGH_LIQUIDITY
    from interday_liquidity_screener.config import ScreenerConfig
    from interday_liquidity_screener.downloader import download_ticker_data
    from interday_liquidity_screener.hybrid_screener import build_hybrid_watchlist, load_hybrid_config, run_hybrid_screener
    from interday_liquidity_screener.llm_analyst import run_llm_report, run_stage6_build_evidence
    from interday_liquidity_screener.metrics import compute_metrics
    from interday_liquidity_screener.orderbook_filter import OrderbookFilterConfig, run_stage3c_orderbook_filter
    from interday_liquidity_screener.paper_bpjs import BpjsPaperConfig, run_stage5_paper_bpjs
    from interday_liquidity_screener.reporting import build_result_frame, save_csv
    from interday_liquidity_screener.stockbit_collector import (
        StockbitCollectorConfig,
        parse_windows_arg,
        run_stage3a_broker_collector_multi_window,
    )
    from interday_liquidity_screener.technical import run_stage_2_technical_screening
    from interday_liquidity_screener.ticker_universe import UNIVERSE_PRESETS, get_universe_preset, read_universe_text
    from interday_liquidity_screener.tickers import load_tickers, normalize_ticker
    from interday_liquidity_screener.trade_plan import TradePlanConfig, run_stage_4_trade_plan
    from interday_liquidity_screener.constants import PipelineStage, WatchlistStatus

APP_TITLE = "Interday Trading Dashboard"
DEFAULT_RUN_ROOT = Path("data/output/ui_runs")
DEFAULT_INPUT_ROOT = Path("data/input")
DEFAULT_MARKET_DATA_DB = Path("data/cache/market_data.sqlite")

STAGE_FILES = {
    "stage1": "stage1_liquidity.csv",
    "stage2": "stage2_technical_context.csv",
    "stage3a_detector": "stage3a_bandar_detector_summary.csv",
    "stage3a_broker": "stage3a_broker_summary_long.csv",
    "stage3b": "stage3b_bandarmology_score.csv",
    "stage3c": "stage3c_orderbook_filter.csv",
    "stage4": "stage4_trade_plan.csv",
    "hybrid_watchlist": "hybrid_watchlist.csv",
    "stage5_trades": "stage5_interday_trades.csv",
    "stage5_metrics": "stage5_interday_metrics.json",
    "stage5_equity": "stage5_interday_equity_curve.csv",
    "stage5_bpjs_paper": "stage5_bpjs_paper_trades.csv",
    "stage5_bpjs_summary": "stage5_bpjs_daily_summary.json",
    "stage6_evidence": "stage6_evidence_pack.json",
    "stage6_report": "stage6_llm_daily_report.md",
    "stage6_ranking": "stage6_llm_candidate_ranking.json",
    "stage6_watchlist": "stage6_llm_watchlist_notes.csv",
    "stage6_raw": "stage6_llm_raw_response.json",
}

HELP_TEXT = {
    "run_output_root": "Folder tempat hasil setiap run disimpan. Aman dibiarkan default.",
    "market_data_db": "Database lokal berisi harga/volume yang pernah diambil. Ini mengurangi penarikan ulang ke API.",
    "run_date": "Tanggal analisis. Biasanya pakai tanggal hari bursa terakhir yang ingin dicek.",
    "strategy": "interday = rencana beberapa hari. bpjs = rencana cepat/intraday yang lebih ketat.",
    "dry_run_llm": "Jika aktif, laporan AI dibuat simulasi tanpa memanggil API berbayar/eksternal.",
    "refresh_market_data": "Jika aktif, harga/volume ditarik ulang dari sumber data walau sudah ada di cache lokal.",
    "stockbit_token_input": "Tempel token Stockbit di sini kalau token di .env sudah berubah. Input ini hanya dipakai untuk sesi dashboard lokal dan tidak disimpan.",
    "deepseek_key_input": "Tempel API key DeepSeek di sini kalau ingin menjalankan laporan AI non-simulasi. Input ini hanya dipakai untuk sesi dashboard lokal dan tidak disimpan.",
    "capital": "Modal simulasi untuk menghitung ukuran posisi. Default 500 ribu agar saham yang terlalu mahal untuk minimal 1 lot otomatis tersaring.",
    "risk_per_trade_pct": "Batas risiko per saham. 0.005 berarti maksimal sekitar 0.5% modal berisiko dalam satu ide trade.",
    "max_position_pct": "Batas maksimal modal yang boleh dipakai untuk satu saham.",
    "bandarmology_min_score": "Nilai minimal sinyal broker-flow. Makin tinggi, filter makin ketat.",
    "ticker_file": "File daftar kode saham, contoh BBCA atau BBCA.JK. Bisa TXT atau CSV.",
    "ticker_universe": "Pilih sumber daftar saham: manual/upload, semua IDX, syariah, LQ45, IDX30, IDX80, JII, dan indeks lain dari file lokal.",
    "ticker_upload": "Upload file ticker dari komputer. Isi file akan masuk ke editor di bawah.",
    "ticker_editor": "Daftar saham yang akan dicek. Satu ticker per baris; sistem akan otomatis menambah .JK.",
    "stages": "Tahapan pipeline. Jalankan semua untuk workflow lengkap, atau pilih beberapa tahap saja.",
    "stage1_period": "Seberapa jauh data historis dipakai untuk screening likuiditas awal. 3mo = 3 bulan.",
    "stage2_period": "Seberapa jauh data historis dipakai untuk indikator teknikal/backtest. 1y = 1 tahun.",
    "stage3a_windows": "Jendela waktu broker-flow. 1D berarti hari terakhir, 20D berarti sekitar 20 hari bursa.",
    "stockbit_sleep": "Jeda antar request Stockbit supaya tidak terlalu agresif ke API.",
    "orderbook_sleep": "Jeda antar request orderbook Stockbit.",
    "inspect_run": "Pilih folder hasil run yang ingin dibaca di tab Overview, Results, dan Reports.",
    "hybrid_mode": "Mode hybrid menentukan seberapa ketat filter akhir. BPJS live wajib punya orderbook.",
    "hybrid_capital_profile": "Profil modal kecil untuk menghitung lot, net profit setelah fee, dan saham yang terlalu mahal.",
    "hybrid_config": "File konfigurasi threshold hybrid screener. Default memakai config/screener.yml.",
    "hybrid_source": "Sumber CSV kandidat. Stage 2 dipakai sebagai basis, lalu broker-flow/orderbook digabung jika tersedia.",
}

STAGE_EXPLANATIONS = {
    "Stage 1": "Cek likuiditas: mana saham yang cukup ramai ditransaksikan.",
    "Stage 2": "Cek teknikal: trend, momentum, volatilitas, dan konteks entry.",
    "Stage 3A": "Ambil data broker-flow dari Stockbit untuk saham yang layak dipantau.",
    "Stage 3B": "Ubah broker-flow menjadi skor akumulasi/distribusi.",
    "Stage 3C": "Cek kualitas orderbook: spread, bid/offer, notasi, dan risiko eksekusi.",
    "Stage 4": "Buat rencana trade: entry, stop loss, take profit, ukuran posisi.",
    "Stage Hybrid": "Gabungkan Safe Execution Flow, Smart Money Discovery Flow, orderbook, fee, dan risk gate menjadi watchlist final.",
    "Stage 5": "Backtest/paper journal untuk melihat simulasi hasil setelah sinyal.",
    "Stage 6": "Buat evidence pack dan laporan AI/dry-run dari hasil pipeline.",
}

FILTER_LABELS = {
    "liquidity_bucket": "Level likuiditas",
    "trade_candidate_bucket": "Status kandidat trade",
    "entry_setup": "Jenis setup entry",
    "technical_context": "Konteks teknikal",
    "bandarmology_signal": "Sinyal broker-flow",
    "orderbook_status": "Status orderbook",
    "trade_status": "Status rencana trade",
    "backtest_status": "Status backtest",
    "final_status": "Status hybrid",
    "flow_source": "Sumber flow hybrid",
    "mode": "Mode hybrid",
    "capital_profile": "Profil modal",
}

FILTER_HELP = {
    "liquidity_bucket": "Seberapa ramai dan konsisten transaksi saham.",
    "trade_candidate_bucket": "Apakah saham layak dipantau dari sisi likuiditas awal.",
    "entry_setup": "Pola teknikal yang terdeteksi, misalnya breakout/pullback/rebound.",
    "technical_context": "Ringkasan kondisi chart sebelum dicek broker-flow.",
    "bandarmology_signal": "Apakah broker-flow cenderung akumulasi, netral, atau distribusi.",
    "orderbook_status": "Apakah kondisi bid/offer mendukung eksekusi.",
    "trade_status": "Alasan final apakah rencana trade valid, ditunggu, atau ditolak.",
    "backtest_status": "Apa yang terjadi saat sinyal diuji ke data harga berikutnya.",
    "final_status": "Keputusan akhir hybrid screener, seperti READY_SOON, NEED_ORDERBOOK, atau EXECUTION_READY.",
    "flow_source": "Apakah kandidat datang dari Safe Execution Flow, Smart Money Discovery Flow, atau keduanya.",
    "mode": "Mode run hybrid yang dipakai saat scoring.",
    "capital_profile": "Profil modal yang dipakai untuk lot, fee, dan net-profit gate.",
}

ARTIFACT_ALIASES = {
    "stage4": ["stage4_trade_plan.csv", "stage4_trade_plan_interday.csv", "stage4_trade_plan_bpjs.csv"],
    "hybrid_watchlist": ["hybrid_watchlist.csv", "stage_hybrid_watchlist.csv"],
    "stage6_evidence": ["stage6_evidence_pack.json", "stage6_bpjs_evidence_pack.json"],
    "stage6_report": ["stage6_llm_daily_report.md", "stage6_bpjs_llm_daily_report.md"],
    "stage6_ranking": ["stage6_llm_candidate_ranking.json", "stage6_bpjs_llm_candidate_ranking.json"],
    "stage6_watchlist": ["stage6_llm_watchlist_notes.csv", "stage6_bpjs_llm_watchlist_notes.csv"],
    "stage6_raw": ["stage6_llm_raw_response.json", "stage6_bpjs_llm_raw_response.json"],
}


@dataclass(frozen=True)
class PipelinePaths:
    run_id: str
    run_dir: Path
    ticker_input: Path
    raw_stockbit: Path
    raw_orderbook: Path
    stage1: Path
    stage2: Path
    stage3a_dir: Path
    stage3a_detector: Path
    stage3a_broker: Path
    stage3b: Path
    stage3c: Path
    stage4: Path
    hybrid_watchlist: Path
    stage5_trades: Path
    stage5_metrics: Path
    stage5_equity: Path
    stage5_bpjs_paper: Path
    stage5_bpjs_summary: Path
    stage6_evidence: Path
    stage6_report: Path
    stage6_ranking: Path
    stage6_watchlist: Path
    stage6_raw: Path


@dataclass(frozen=True)
class StageRunResult:
    name: str
    ok: bool
    log: str
    output_path: Path | None = None
    error: str | None = None


@dataclass(frozen=True)
class PipelineOptions:
    tickers_file: Path
    run_root: Path = DEFAULT_RUN_ROOT
    market_data_db: Path = DEFAULT_MARKET_DATA_DB
    run_date: str = date.today().isoformat()
    period_stage1: str = "3mo"
    period_stage2: str = "1y"
    windows: str = "1D,3D,5D,10D,20D"
    strategy_mode: str = "interday"
    capital: float = 500_000
    risk_per_trade_pct: float | None = None
    max_position_pct: float | None = None
    bandarmology_min_score: int = 50
    stockbit_sleep_seconds: float = 3.0
    orderbook_sleep_seconds: float = 2.0
    dry_run_llm: bool = True
    refresh_market_data: bool = False
    allow_trade_without_broker_data: bool = False
    require_orderbook_confirmation: bool | None = None
    strict_corporate_action_filter: bool = False
    hybrid_mode: str = "normal_execution"
    hybrid_capital_profile: str = "capital_1m"
    hybrid_config_path: Path = Path("config/screener.yml")
    hybrid_max_candidates: int | None = None
    enable_market_regime: bool | None = None
    enable_multibar_confirm: bool | None = None
    enable_adaptive_tp: bool | None = None
    enable_liquidity_sizer: bool | None = None
    enable_blackout: bool | None = None


def create_run_id(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d_%H%M%S")


def build_run_paths(run_root: str | Path = DEFAULT_RUN_ROOT, run_id: str | None = None) -> PipelinePaths:
    resolved_run_id = run_id or create_run_id()
    run_dir = Path(run_root) / resolved_run_id
    stage3a_dir = run_dir / "stockbit"
    return PipelinePaths(
        run_id=resolved_run_id,
        run_dir=run_dir,
        ticker_input=DEFAULT_INPUT_ROOT / f"ui_tickers_{resolved_run_id}.txt",
        raw_stockbit=run_dir / "raw_stockbit",
        raw_orderbook=run_dir / "raw_stockbit_orderbook",
        stage1=run_dir / STAGE_FILES["stage1"],
        stage2=run_dir / STAGE_FILES["stage2"],
        stage3a_dir=stage3a_dir,
        stage3a_detector=stage3a_dir / STAGE_FILES["stage3a_detector"],
        stage3a_broker=stage3a_dir / STAGE_FILES["stage3a_broker"],
        stage3b=run_dir / STAGE_FILES["stage3b"],
        stage3c=run_dir / STAGE_FILES["stage3c"],
        stage4=run_dir / STAGE_FILES["stage4"],
        hybrid_watchlist=run_dir / STAGE_FILES["hybrid_watchlist"],
        stage5_trades=run_dir / STAGE_FILES["stage5_trades"],
        stage5_metrics=run_dir / STAGE_FILES["stage5_metrics"],
        stage5_equity=run_dir / STAGE_FILES["stage5_equity"],
        stage5_bpjs_paper=run_dir / STAGE_FILES["stage5_bpjs_paper"],
        stage5_bpjs_summary=run_dir / STAGE_FILES["stage5_bpjs_summary"],
        stage6_evidence=run_dir / STAGE_FILES["stage6_evidence"],
        stage6_report=run_dir / STAGE_FILES["stage6_report"],
        stage6_ranking=run_dir / STAGE_FILES["stage6_ranking"],
        stage6_watchlist=run_dir / STAGE_FILES["stage6_watchlist"],
        stage6_raw=run_dir / STAGE_FILES["stage6_raw"],
    )


def token_available(name: str, env_path: str | Path = ".env") -> bool:
    if os.environ.get(name, "").strip():
        return True
    path = Path(env_path)
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() == name and value.strip().strip('"').strip("'"):
            return True
    return False


def _clean_runtime_secret(name: str, value: str) -> str:
    cleaned = value.strip().strip('"').strip("'")
    if name == "STOCKBIT_TOKEN" and cleaned.lower().startswith("bearer "):
        return cleaned[7:].strip()
    return cleaned


def apply_runtime_api_keys(stockbit_token: str = "", deepseek_api_key: str = "") -> None:
    values = {
        "STOCKBIT_TOKEN": stockbit_token,
        "DEEPSEEK_API_KEY": deepseek_api_key,
    }
    for name, raw_value in values.items():
        marker = f"_UI_{name}_APPLIED"
        cleaned = _clean_runtime_secret(name, raw_value)
        if cleaned:
            os.environ[name] = cleaned
            os.environ[marker] = "1"
        elif os.environ.get(marker) == "1":
            os.environ.pop(name, None)
            os.environ.pop(marker, None)


def parse_ticker_text(text: str) -> list[str]:
    tickers: set[str] = set()
    for raw in text.replace(",", "\n").splitlines():
        ticker = normalize_ticker(raw)
        if ticker:
            tickers.add(ticker)
    return sorted(tickers)


def write_ticker_input(tickers: list[str], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(tickers) + "\n", encoding="utf-8")
    return output_path


def discover_run_dirs(run_root: str | Path = DEFAULT_RUN_ROOT) -> list[Path]:
    roots = [Path(run_root)]
    if Path(run_root) == DEFAULT_RUN_ROOT:
        roots.append(Path("data/output"))
    found: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.iterdir():
            if path.is_dir() and _has_known_artifact(path):
                found.append(path)
    return sorted(set(found), reverse=True)


def resolve_artifact_path(run_dir: str | Path, artifact: str) -> Path:
    root = Path(run_dir)
    if artifact.startswith("stage3a_"):
        candidates = [root / "stockbit" / name for name in ARTIFACT_ALIASES.get(artifact, [STAGE_FILES[artifact]])]
    else:
        candidates = [root / name for name in ARTIFACT_ALIASES.get(artifact, [STAGE_FILES[artifact]])]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def _has_known_artifact(path: Path) -> bool:
    return any(resolve_artifact_path(path, artifact).exists() for artifact in ["stage1", "stage2", "stage4", "hybrid_watchlist", "stage6_report"])


def load_csv(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(file_path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def load_json(path: str | Path) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def summarize_run(run_dir: str | Path) -> dict[str, Any]:
    root = Path(run_dir)
    stage1 = load_csv(resolve_artifact_path(root, "stage1"))
    stage2 = load_csv(resolve_artifact_path(root, "stage2"))
    stage4 = load_csv(resolve_artifact_path(root, "stage4"))
    hybrid = load_csv(resolve_artifact_path(root, "hybrid_watchlist"))
    metrics = load_json(resolve_artifact_path(root, "stage5_metrics"))
    report_path = resolve_artifact_path(root, "stage6_report")
    return {
        "run": root.name,
        "stage1_rows": int(len(stage1)),
        "liquid_rows": _count_in(stage1, "liquidity_bucket", {HIGH_LIQUIDITY, GOOD_LIQUIDITY}),
        "stage2_rows": int(len(stage2)),
        "bandar_watch": _sum_bool(stage2, "bandar_watch_eligible"),
        "valid_trade_plans": _count_in(stage4, "trade_status", {"VALID_TRADE_PLAN"}),
        "hybrid_ready": _count_in(hybrid, "final_status", {WatchlistStatus.EXECUTION_READY}),
        "hybrid_watch_rows": int(len(hybrid)),
        "closed_trades": metrics.get("entry_triggered_count", 0),
        "win_rate": metrics.get("win_rate"),
        "report_available": report_path.exists(),
    }


def _count_in(df: pd.DataFrame, column: str, values: set[Any]) -> int:
    if df.empty or column not in df.columns:
        return 0
    return int(df[column].isin(values).sum())


def _sum_bool(df: pd.DataFrame, column: str) -> int:
    if df.empty or column not in df.columns:
        return 0
    return int(df[column].astype(str).str.lower().isin({"true", "1", "yes"}).sum())


def capture_stage(name: str, output_path: Path | None, func: Callable[[], Any], resume: bool = False) -> StageRunResult:
    if resume and output_path:
        is_valid = False
        if output_path.is_file() and output_path.exists() and output_path.stat().st_size > 0:
            is_valid = True
        elif output_path.is_dir() and output_path.exists() and any(output_path.iterdir()):
            is_valid = True
            
        if is_valid:
            msg = f"[SKIP] Reused existing output for '{name}' from {output_path.name}\n"
            print(msg.strip())
            return StageRunResult(name=name, ok=True, log=msg, output_path=output_path)

    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer):
            func()
        return StageRunResult(name=name, ok=True, log=buffer.getvalue(), output_path=output_path)
    except Exception as exc:
        return StageRunResult(name=name, ok=False, log=buffer.getvalue(), output_path=output_path, error=str(exc))


def is_morning_live_refresh(stage_names: list[str], resume: bool) -> bool:
    """Return whether a resumed selection must refresh live morning artifacts."""
    stage_set = {
        stage.value if isinstance(stage, PipelineStage) else str(stage)
        for stage in stage_names
    }
    preparation_stages = {
        PipelineStage.STAGE1.value,
        PipelineStage.STAGE2.value,
        PipelineStage.STAGE3A.value,
        PipelineStage.STAGE3B.value,
    }
    return (
        resume
        and PipelineStage.STAGE3C.value in stage_set
        and preparation_stages.isdisjoint(stage_set)
    )


def run_stage1_screening(tickers_file: str | Path, output_path: str | Path, options: PipelineOptions) -> pd.DataFrame:
    config = ScreenerConfig(
        period=options.period_stage1,
        interval="1d",
        batch_size=50,
        market_data_db=str(options.market_data_db),
        refresh_market_data=options.refresh_market_data,
    )
    tickers = load_tickers(tickers_file)
    print(f"Total tickers loaded: {len(tickers)}")
    data_map = download_ticker_data(tickers, config)
    rows = [compute_metrics(ticker, data_map.get(ticker), config) for ticker in tickers]
    output = build_result_frame(rows)
    save_csv(output, output_path)
    print(f"Stage 1 output saved to: {output_path}")
    return output


def run_pipeline(
    options: PipelineOptions,
    stage_names: list[str] | None = None,
    paths: PipelinePaths | None = None,
    resume: bool = False,
) -> tuple[PipelinePaths, list[StageRunResult]]:
    selected_stages = stage_names or ["stage1", "stage2", "stage3a", "stage3b", "stage3c", "stage4", "hybrid", "stage5", "stage6"]
    stage_set = set(selected_stages)
    if is_morning_live_refresh(selected_stages, resume):
        # Refresh Stage 3C and every selected downstream artifact. This keeps
        # CLI and MCP morning runs consistent with the dashboard behavior.
        resume = False
    paths = paths or build_run_paths(options.run_root)
    paths.run_dir.mkdir(parents=True, exist_ok=True)
    results: list[StageRunResult] = []

    if "stage1" in stage_set:
        results.append(capture_stage("Stage 1 - Liquidity", paths.stage1, lambda: run_stage1_screening(options.tickers_file, paths.stage1, options), resume=resume))
    if _last_failed(results):
        return paths, results

    if "stage2" in stage_set:
        results.append(
            capture_stage(
                "Stage 2 - Technical",
                paths.stage2,
                lambda: run_stage_2_technical_screening(
                    paths.stage1,
                    paths.stage2,
                    period=options.period_stage2,
                    market_data_db=options.market_data_db,
                    refresh_market_data=options.refresh_market_data,
                ),
                resume=resume,
            )
        )
    if _last_failed(results):
        return paths, results

    if "stage3a" in stage_set:
        config = StockbitCollectorConfig(sleep_seconds=options.stockbit_sleep_seconds)
        results.append(
            capture_stage(
                "Stage 3A - Stockbit Broker",
                paths.stage3a_broker,
                lambda: run_stage3a_broker_collector_multi_window(
                    paths.stage2,
                    paths.stage3a_dir,
                    paths.raw_stockbit,
                    options.run_date,
                    parse_windows_arg(options.windows),
                    config,
                ),
                resume=resume,
            )
        )
    if _last_failed(results):
        return paths, results

    if "stage3b" in stage_set:
        results.append(
            capture_stage(
                "Stage 3B - Bandarmology",
                paths.stage3b,
                lambda: run_stage3b_bandarmology_scoring(paths.stage2, paths.stage3a_detector, paths.stage3a_broker, paths.stage3b),
                resume=resume,
            )
        )
    if _last_failed(results):
        return paths, results

    if "stage3c" in stage_set:
        config = OrderbookFilterConfig(sleep_seconds=options.orderbook_sleep_seconds)
        results.append(
            capture_stage(
                "Stage 3C - Orderbook",
                paths.stage3c,
                lambda: run_stage3c_orderbook_filter(
                    paths.stage2,
                    paths.stage3b,
                    paths.stage3c,
                    paths.raw_orderbook,
                    config,
                    watchlist_path=paths.hybrid_watchlist,
                ),
                resume=resume,
            )
        )
    if _last_failed(results):
        return paths, results

    if "stage4" in stage_set:
        config = TradePlanConfig(
            strategy_mode=options.strategy_mode,
            capital=options.capital,
            risk_per_trade_pct=options.risk_per_trade_pct,
            max_position_pct=options.max_position_pct,
            bandarmology_min_score=options.bandarmology_min_score,
            allow_trade_without_broker_data=options.allow_trade_without_broker_data,
            require_orderbook_confirmation=options.require_orderbook_confirmation,
            strict_corporate_action_filter=options.strict_corporate_action_filter,
        )
        results.append(
            capture_stage(
                "Stage 4 - Trade Plan",
                paths.stage4,
                lambda: run_stage_4_trade_plan(paths.stage2, paths.stage3b, paths.stage4, config=config, orderbook_path=paths.stage3c),
                resume=resume,
            )
        )
    if _last_failed(results):
        return paths, results

    if "hybrid" in stage_set:
        broker_path = paths.stage3b if paths.stage3b.exists() else None
        orderbook_path = paths.stage3c if paths.stage3c.exists() else None
        results.append(
            capture_stage(
                "Stage Hybrid - Dual Flow Watchlist",
                paths.hybrid_watchlist,
                lambda: run_hybrid_screener(
                            input_path=paths.stage4 if paths.stage4.exists() else paths.stage2,
                    output_path=paths.hybrid_watchlist,
                    mode=options.hybrid_mode,
                    capital_profile=options.hybrid_capital_profile,
                    config_path=options.hybrid_config_path,
                            broker_flow_path=None if paths.stage4.exists() else broker_path,
                            orderbook_path=None if paths.stage4.exists() else orderbook_path,
                    date=options.run_date,
                    max_candidates=options.hybrid_max_candidates,
                    enable_market_regime=options.enable_market_regime,
                    enable_multibar_confirm=options.enable_multibar_confirm,
                    enable_adaptive_tp=options.enable_adaptive_tp,
                    enable_liquidity_sizer=options.enable_liquidity_sizer,
                            enable_blackout=options.enable_blackout,
                            capital=options.capital,
                            risk_per_trade_pct=options.risk_per_trade_pct,
                            max_position_pct=options.max_position_pct,
                ),
                resume=resume,
            )
        )
    if _last_failed(results):
        return paths, results

    if "stage5" in stage_set:
        backtest_config = InterdayBacktestConfig(
            period=options.period_stage2,
            initial_capital=options.capital,
            market_data_db=options.market_data_db,
            refresh_price_cache=options.refresh_market_data,
        )
        results.append(
            capture_stage(
                "Stage 5A - Interday Backtest",
                paths.stage5_trades,
                lambda: run_stage5_backtest_interday(
                    paths.stage4,
                    paths.stage5_trades,
                    paths.stage5_metrics,
                    paths.stage5_equity,
                    backtest_config,
                ),
                resume=resume,
            )
        )
        bpjs_config = BpjsPaperConfig(date=options.run_date)
        results.append(
            capture_stage(
                "Stage 5B - BPJS Paper",
                paths.stage5_bpjs_paper,
                lambda: run_stage5_paper_bpjs(
                    paths.stage4,
                    paths.stage3c if paths.stage3c.exists() and paths.stage3c.stat().st_size > 10 else None,
                    paths.stage5_bpjs_paper,
                    bpjs_config,
                    summary_output_path=paths.stage5_bpjs_summary,
                ),
                resume=resume,
            )
        )
    if _last_failed(results):
        return paths, results

    if "stage6" in stage_set:
        results.append(
            capture_stage(
                "Stage 6A - Evidence",
                paths.stage6_evidence,
                lambda: run_stage6_build_evidence(
                    paths.stage2,
                    paths.stage3b if paths.stage3b.exists() else None,
                    paths.stage3c if paths.stage3c.exists() and paths.stage3c.stat().st_size > 10 else None,
                    paths.stage4,
                    paths.stage5_metrics if paths.stage5_metrics.exists() else None,
                    paths.stage5_bpjs_summary if paths.stage5_bpjs_summary.exists() else None,
                    paths.stage6_evidence,
                    options.strategy_mode,
                    options.run_date,
                    30,
                ),
                resume=resume,
            )
        )
        results.append(
            capture_stage(
                "Stage 6B - LLM Report",
                paths.stage6_report,
                lambda: run_llm_report(
                    paths.stage6_evidence,
                    paths.stage6_report,
                    paths.stage6_ranking,
                    paths.stage6_watchlist,
                    paths.stage6_raw,
                    options.strategy_mode,
                    dry_run=options.dry_run_llm,
                ),
                resume=resume,
            )
        )
    return paths, results


def _last_failed(results: list[StageRunResult]) -> bool:
    return bool(results and not results[-1].ok)


