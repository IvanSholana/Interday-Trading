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
    risk_per_trade_pct: float = 0.005
    max_position_pct: float = 0.20
    bandarmology_min_score: int = 60
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
        "hybrid_ready": _count_in(hybrid, "final_status", {"EXECUTION_READY"}),
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


def capture_stage(name: str, output_path: Path | None, func: Callable[[], Any]) -> StageRunResult:
    buffer = io.StringIO()
    try:
        with redirect_stdout(buffer):
            func()
        return StageRunResult(name=name, ok=True, log=buffer.getvalue(), output_path=output_path)
    except Exception as exc:
        return StageRunResult(name=name, ok=False, log=buffer.getvalue(), output_path=output_path, error=str(exc))


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
) -> tuple[PipelinePaths, list[StageRunResult]]:
    stage_set = set(stage_names or ["stage1", "stage2", "stage3a", "stage3b", "stage3c", "stage4", "hybrid", "stage5", "stage6"])
    paths = paths or build_run_paths(options.run_root)
    paths.run_dir.mkdir(parents=True, exist_ok=True)
    results: list[StageRunResult] = []

    if "stage1" in stage_set:
        results.append(capture_stage("Stage 1 - Liquidity", paths.stage1, lambda: run_stage1_screening(options.tickers_file, paths.stage1, options)))
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
                lambda: run_stage3c_orderbook_filter(paths.stage2, paths.stage3b, paths.stage3c, paths.raw_orderbook, config),
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
                    input_path=paths.stage2,
                    output_path=paths.hybrid_watchlist,
                    mode=options.hybrid_mode,
                    capital_profile=options.hybrid_capital_profile,
                    config_path=options.hybrid_config_path,
                    broker_flow_path=broker_path,
                    orderbook_path=orderbook_path,
                    date=options.run_date,
                    max_candidates=options.hybrid_max_candidates,
                ),
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
            )
        )
        bpjs_config = BpjsPaperConfig(date=options.run_date)
        results.append(
            capture_stage(
                "Stage 5B - BPJS Paper",
                paths.stage5_bpjs_paper,
                lambda: run_stage5_paper_bpjs(
                    paths.stage4,
                    paths.stage3c if paths.stage3c.exists() else None,
                    paths.stage5_bpjs_paper,
                    bpjs_config,
                    summary_output_path=paths.stage5_bpjs_summary,
                ),
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
                    paths.stage3c if paths.stage3c.exists() else None,
                    paths.stage4,
                    paths.stage5_metrics if paths.stage5_metrics.exists() else None,
                    paths.stage5_bpjs_summary if paths.stage5_bpjs_summary.exists() else None,
                    paths.stage6_evidence,
                    options.strategy_mode,
                    options.run_date,
                    30,
                ),
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
            )
        )
    return paths, results


def _last_failed(results: list[StageRunResult]) -> bool:
    return bool(results and not results[-1].ok)


def launch() -> None:
    from streamlit.web import cli as stcli

    app_path = Path(__file__).resolve()
    sys.argv = ["streamlit", "run", str(app_path)]
    stcli.main()


def main() -> None:
    try:
        import streamlit as st
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError("Streamlit is not installed. Run: python -m pip install -e .") from exc

    _render_app(st)


def _render_app(st: Any) -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="IDX", layout="wide")
    _inject_css(st)

    st.title(APP_TITLE)
    st.caption("Local pipeline dashboard for IDX liquidity, bandarmology, trade plan, backtest, and LLM review.")
    _render_plain_language_guide(st)

    sidebar = _render_sidebar(st)
    run_dirs = discover_run_dirs(sidebar["run_root"])
    selected_run_dir = _resolve_selected_run(st, run_dirs)

    tabs = st.tabs(["Run Pipeline", "Hybrid Screener", "Overview", "Results Explorer", "Reports", "Cache & Settings"])
    with tabs[0]:
        _render_run_pipeline(st, sidebar)
    with tabs[1]:
        _render_hybrid_screener(st, sidebar, selected_run_dir)
    with tabs[2]:
        _render_overview(st, selected_run_dir)
    with tabs[3]:
        _render_results_explorer(st, selected_run_dir)
    with tabs[4]:
        _render_reports(st, selected_run_dir)
    with tabs[5]:
        _render_cache_settings(st, sidebar, selected_run_dir)


def _render_sidebar(st: Any) -> dict[str, Any]:
    st.sidebar.header("Global Settings")
    run_root = Path(st.sidebar.text_input("Folder hasil run", value=str(DEFAULT_RUN_ROOT), help=HELP_TEXT["run_output_root"]))
    market_data_db = Path(st.sidebar.text_input("Database harga lokal", value=str(DEFAULT_MARKET_DATA_DB), help=HELP_TEXT["market_data_db"]))
    run_date = st.sidebar.date_input("Tanggal analisis", value=date.today(), help=HELP_TEXT["run_date"]).isoformat()
    strategy_mode = st.sidebar.radio("Strategi", options=["interday", "bpjs"], horizontal=True, help=HELP_TEXT["strategy"])
    dry_run_llm = st.sidebar.toggle("Laporan AI simulasi", value=True, help=HELP_TEXT["dry_run_llm"])
    refresh_market_data = st.sidebar.toggle("Ambil ulang harga dari API", value=False, help=HELP_TEXT["refresh_market_data"])

    with st.sidebar.expander("Pengaturan risiko", expanded=False):
        capital = st.number_input("Modal simulasi", min_value=100_000.0, value=500_000.0, step=100_000.0, help=HELP_TEXT["capital"])
        risk_per_trade_pct = st.number_input("Risiko per trade", min_value=0.001, max_value=0.05, value=0.005, step=0.001, format="%.4f", help=HELP_TEXT["risk_per_trade_pct"])
        max_position_pct = st.number_input("Batas posisi per saham", min_value=0.01, max_value=1.0, value=0.20, step=0.01, format="%.2f", help=HELP_TEXT["max_position_pct"])
        bandarmology_min_score = st.number_input("Skor broker-flow minimal", min_value=0, max_value=100, value=60, step=5, help=HELP_TEXT["bandarmology_min_score"])

    with st.sidebar.expander("Token/API key sementara", expanded=False):
        st.caption("Tidak disimpan ke file. Kosongkan lagi untuk kembali memakai token dari .env.")
        stockbit_token_input = st.text_area(
            "Stockbit token",
            value="",
            height=88,
            placeholder="Tempel token Stockbit baru di sini",
            help=HELP_TEXT["stockbit_token_input"],
        )
        deepseek_key_input = st.text_input(
            "DeepSeek API key",
            value="",
            type="password",
            placeholder="Tempel API key DeepSeek",
            help=HELP_TEXT["deepseek_key_input"],
        )
    apply_runtime_api_keys(stockbit_token_input, deepseek_key_input)

    stockbit_ok = token_available("STOCKBIT_TOKEN")
    deepseek_ok = token_available("DEEPSEEK_API_KEY")
    st.sidebar.divider()
    st.sidebar.write("Status token API")
    if stockbit_ok:
        st.sidebar.success("Stockbit siap dipakai")
    else:
        st.sidebar.error("Token Stockbit belum ada")
    if deepseek_ok:
        st.sidebar.success("DeepSeek siap dipakai")
    else:
        st.sidebar.warning("Token DeepSeek belum ada")

    return {
        "run_root": run_root,
        "market_data_db": market_data_db,
        "run_date": run_date,
        "strategy_mode": strategy_mode,
        "dry_run_llm": dry_run_llm,
        "refresh_market_data": refresh_market_data,
        "capital": capital,
        "risk_per_trade_pct": risk_per_trade_pct,
        "max_position_pct": max_position_pct,
        "bandarmology_min_score": int(bandarmology_min_score),
        "stockbit_ok": stockbit_ok,
        "deepseek_ok": deepseek_ok,
    }


def _resolve_selected_run(st: Any, run_dirs: list[Path]) -> Path | None:
    if not run_dirs:
        return None
    latest = st.session_state.get("latest_run_dir")
    options = [str(path) for path in run_dirs]
    index = options.index(latest) if latest in options else 0
    selected = st.sidebar.selectbox("Baca hasil run", options=options, index=index, help=HELP_TEXT["inspect_run"])
    return Path(selected)


def _render_plain_language_guide(st: Any) -> None:
    with st.expander("Panduan istilah sederhana", expanded=False):
        st.markdown(
            """
            - **Pipeline / Stage**: urutan kerja dari cek saham ramai, cek teknikal, cek broker-flow, sampai jadi rencana trade.
            - **Cache / database harga lokal**: tempat menyimpan harga yang sudah pernah diambil, supaya API tidak dipanggil terus.
            - **Interday**: rencana trade untuk ditahan beberapa hari.
            - **BPJS**: mode cepat/intraday yang lebih ketat, butuh orderbook lebih mendukung.
            - **Bandarmology / broker-flow**: membaca kecenderungan broker sedang akumulasi, netral, atau distribusi.
            - **Orderbook**: antrean bid/offer. Dipakai untuk menilai apakah saham mudah dieksekusi.
            - **Dry-run LLM**: membuat laporan contoh tanpa memanggil API AI eksternal.
            - **Backtest**: simulasi aturan trade memakai data harga historis.
            """
        )


def _render_run_pipeline(st: Any, sidebar: dict[str, Any]) -> None:
    st.subheader("Run Pipeline")
    st.write("Pilih daftar saham, atur opsi yang penting saja, lalu jalankan analisis lokal.")

    stage_options = {
        "Stage 1": "stage1",
        "Stage 2": "stage2",
        "Stage 3A": "stage3a",
        "Stage 3B": "stage3b",
        "Stage 3C": "stage3c",
        "Stage 4": "stage4",
        "Stage Hybrid": "hybrid",
        "Stage 5": "stage5",
        "Stage 6": "stage6",
    }

    left, right = st.columns([1.2, 1])
    with left:
        universe_labels = [preset.label for preset in UNIVERSE_PRESETS]
        universe_by_label = {preset.label: preset for preset in UNIVERSE_PRESETS}
        selected_universe_label = st.selectbox("Mode daftar saham", universe_labels, index=0, help=HELP_TEXT["ticker_universe"])
        selected_universe = universe_by_label[selected_universe_label]
        default_file = Path("examples/tickers.txt")
        ticker_file_text = st.text_input(
            "File daftar saham manual",
            value=str(default_file),
            help=HELP_TEXT["ticker_file"],
            disabled=selected_universe.key != "manual",
        )
        uploaded = st.file_uploader(
            "Atau upload TXT/CSV",
            type=["txt", "csv"],
            help=HELP_TEXT["ticker_upload"],
            disabled=selected_universe.key != "manual",
        )
        initial_text = _read_universe_or_manual_text(selected_universe.key, uploaded, ticker_file_text)
        if selected_universe.key != "manual":
            preset = get_universe_preset(selected_universe.key)
            st.caption(f"Preset lokal: {preset.path}")
            st.caption(preset.description)
        ticker_text = st.text_area(
            "Editor daftar saham",
            value=initial_text,
            height=240,
            help=HELP_TEXT["ticker_editor"],
            key=f"ticker_editor_{selected_universe.key}",
        )
        tickers = []
        ticker_error = None
        try:
            tickers = parse_ticker_text(ticker_text)
        except ValueError as exc:
            ticker_error = str(exc)
        st.caption(f"Jumlah saham terbaca: {len(tickers)}")
        if ticker_error:
            st.error(ticker_error)

    with right:
        selected_labels = st.multiselect("Tahapan yang dijalankan", list(stage_options.keys()), default=list(stage_options.keys()), help=HELP_TEXT["stages"])
        period_stage1 = st.text_input("Periode cek likuiditas", value="3mo", help=HELP_TEXT["stage1_period"])
        period_stage2 = st.text_input("Periode teknikal/backtest", value="1y", help=HELP_TEXT["stage2_period"])
        windows = st.text_input("Jendela broker-flow", value="1D,3D,5D,10D,20D", help=HELP_TEXT["stage3a_windows"])
        stockbit_sleep = st.number_input("Jeda API Stockbit", min_value=0.0, value=3.0, step=0.5, help=HELP_TEXT["stockbit_sleep"])
        orderbook_sleep = st.number_input("Jeda API orderbook", min_value=0.0, value=2.0, step=0.5, help=HELP_TEXT["orderbook_sleep"])
        hybrid_mode = st.selectbox(
            "Mode hybrid",
            ["normal_execution", "bpjs_live", "smart_money_first", "weekend_preparation", "interday_swing", "hybrid_dual_flow"],
            index=0,
            help=HELP_TEXT["hybrid_mode"],
        )
        hybrid_capital_profile = st.selectbox(
            "Profil modal hybrid",
            ["capital_500k", "capital_1m", "capital_1_5m"],
            index=1,
            help=HELP_TEXT["hybrid_capital_profile"],
        )
        hybrid_config_path = st.text_input("Config hybrid", value="config/screener.yml", help=HELP_TEXT["hybrid_config"])
        hybrid_max_candidates = st.number_input("Maks kandidat hybrid", min_value=0, value=0, step=1)

        needs_stockbit = any(stage_options[label] in {"stage3a", "stage3c"} for label in selected_labels)
        needs_llm_api = "Stage 6" in selected_labels and not sidebar["dry_run_llm"]
        disabled = bool(ticker_error) or not tickers or (needs_stockbit and not sidebar["stockbit_ok"]) or (needs_llm_api and not sidebar["deepseek_ok"])
        if needs_stockbit and not sidebar["stockbit_ok"]:
            st.warning("Stage 3A/3C butuh token Stockbit. Isi di sidebar bagian Token/API key sementara.")
        if needs_llm_api and not sidebar["deepseek_ok"]:
            st.warning("Stage 6 non-simulasi butuh DeepSeek API key. Isi di sidebar bagian Token/API key sementara.")
        if st.button("Jalankan analisis", type="primary", disabled=disabled, use_container_width=True):
            paths = build_run_paths(sidebar["run_root"])
            ticker_input = write_ticker_input(tickers, paths.ticker_input)
            options = PipelineOptions(
                tickers_file=ticker_input,
                run_root=sidebar["run_root"],
                market_data_db=sidebar["market_data_db"],
                run_date=sidebar["run_date"],
                period_stage1=period_stage1,
                period_stage2=period_stage2,
                windows=windows,
                strategy_mode=sidebar["strategy_mode"],
                capital=float(sidebar["capital"]),
                risk_per_trade_pct=float(sidebar["risk_per_trade_pct"]),
                max_position_pct=float(sidebar["max_position_pct"]),
                bandarmology_min_score=int(sidebar["bandarmology_min_score"]),
                stockbit_sleep_seconds=float(stockbit_sleep),
                orderbook_sleep_seconds=float(orderbook_sleep),
                dry_run_llm=bool(sidebar["dry_run_llm"]),
                refresh_market_data=bool(sidebar["refresh_market_data"]),
                hybrid_mode=hybrid_mode,
                hybrid_capital_profile=hybrid_capital_profile,
                hybrid_config_path=Path(hybrid_config_path),
                hybrid_max_candidates=int(hybrid_max_candidates) if int(hybrid_max_candidates) > 0 else None,
            )
            stage_names = [stage_options[label] for label in selected_labels]
            with st.spinner("Menjalankan pipeline..."):
                run_paths, results = run_pipeline(options, stage_names, paths=paths)
            st.session_state["latest_run_dir"] = str(run_paths.run_dir)
            st.success(f"Hasil disimpan ke {run_paths.run_dir}")
            _render_stage_results(st, results)
        _render_stage_explanations(st, selected_labels)


def _read_universe_or_manual_text(universe_key: str, uploaded: Any, file_text: str) -> str:
    if universe_key != "manual":
        return read_universe_text(universe_key)
    return _read_uploaded_or_file(uploaded, file_text)


def _read_uploaded_or_file(uploaded: Any, file_text: str) -> str:
    if uploaded is not None:
        return uploaded.getvalue().decode("utf-8")
    path = Path(file_text)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _render_stage_results(st: Any, results: list[StageRunResult]) -> None:
    for result in results:
        state = "complete" if result.ok else "error"
        with st.status(result.name, state=state, expanded=not result.ok):
            if result.output_path:
                st.caption(str(result.output_path))
            if result.error:
                st.error(result.error)
            st.code(result.log or "(no log)", language="text")


def _render_stage_explanations(st: Any, selected_labels: list[str]) -> None:
    if not selected_labels:
        st.info("Pilih minimal satu tahapan analisis.")
        return
    with st.expander("Apa arti tiap Stage?", expanded=False):
        for label in selected_labels:
            st.markdown(f"**{label}** - {STAGE_EXPLANATIONS.get(label, '')}")


def _render_hybrid_screener(st: Any, sidebar: dict[str, Any], run_dir: Path | None) -> None:
    st.subheader("Hybrid Screener")
    st.caption("Safe Execution Flow + Smart Money Discovery Flow + live orderbook/risk/net-profit validation.")

    left, right = st.columns([1, 1])
    with left:
        mode = st.selectbox(
            "Mode",
            ["normal_execution", "bpjs_live", "smart_money_first", "weekend_preparation", "interday_swing", "hybrid_dual_flow"],
            index=0,
            key="hybrid_tab_mode",
            help=HELP_TEXT["hybrid_mode"],
        )
        capital_profile = st.selectbox(
            "Profil modal",
            ["capital_500k", "capital_1m", "capital_1_5m"],
            index=1,
            key="hybrid_tab_capital",
            help=HELP_TEXT["hybrid_capital_profile"],
        )
        config_path = st.text_input("Config", value="config/screener.yml", key="hybrid_tab_config", help=HELP_TEXT["hybrid_config"])
        max_candidates = st.number_input("Maks kandidat", min_value=0, value=0, step=1, key="hybrid_tab_max")

    with right:
        source = st.radio(
            "Sumber data",
            ["Run terpilih", "Upload CSV"],
            horizontal=True,
            help=HELP_TEXT["hybrid_source"],
        )
        run_date = st.text_input("Tanggal output", value=str(sidebar.get("run_date", date.today().isoformat())))
        uploaded_candidates = uploaded_broker = uploaded_orderbook = None
        if source == "Upload CSV":
            uploaded_candidates = st.file_uploader("Candidate CSV", type=["csv"], key="hybrid_candidates_upload")
            uploaded_broker = st.file_uploader("Broker-flow CSV optional", type=["csv"], key="hybrid_broker_upload")
            uploaded_orderbook = st.file_uploader("Orderbook CSV optional", type=["csv"], key="hybrid_orderbook_upload")
        elif run_dir is None:
            st.warning("Belum ada run terpilih. Jalankan pipeline dulu atau upload CSV.")

    existing = load_csv(resolve_artifact_path(run_dir, "hybrid_watchlist")) if run_dir else pd.DataFrame()
    if not existing.empty:
        st.write("Hasil hybrid terakhir di run terpilih")
        _render_hybrid_watchlist_table(st, existing, resolve_artifact_path(run_dir, "hybrid_watchlist"))

    if st.button("Jalankan Hybrid Screener", type="primary", use_container_width=True):
        try:
            output_path = _run_hybrid_from_streamlit(
                st,
                source,
                run_dir,
                uploaded_candidates,
                uploaded_broker,
                uploaded_orderbook,
                mode,
                capital_profile,
                Path(config_path),
                run_date,
                int(max_candidates) if int(max_candidates) > 0 else None,
            )
            result = load_csv(output_path)
            if run_dir:
                st.session_state["latest_run_dir"] = str(run_dir)
            st.success(f"Hybrid watchlist disimpan ke {output_path}")
            _render_hybrid_watchlist_table(st, result, output_path)
        except Exception as exc:
            st.error(str(exc))


def _run_hybrid_from_streamlit(
    st: Any,
    source: str,
    run_dir: Path | None,
    uploaded_candidates: Any,
    uploaded_broker: Any,
    uploaded_orderbook: Any,
    mode: str,
    capital_profile: str,
    config_path: Path,
    run_date: str,
    max_candidates: int | None,
) -> Path:
    if source == "Run terpilih":
        if run_dir is None:
            raise ValueError("Pilih run terlebih dahulu atau gunakan upload CSV.")
        candidate_path = resolve_artifact_path(run_dir, "stage2")
        broker_path = resolve_artifact_path(run_dir, "stage3b")
        orderbook_path = resolve_artifact_path(run_dir, "stage3c")
        if not candidate_path.exists():
            raise FileNotFoundError(f"Stage 2 tidak ditemukan: {candidate_path}")
        output_path = resolve_artifact_path(run_dir, "hybrid_watchlist")
        run_hybrid_screener(
            input_path=candidate_path,
            output_path=output_path,
            mode=mode,
            capital_profile=capital_profile,
            config_path=config_path,
            broker_flow_path=broker_path if broker_path.exists() else None,
            orderbook_path=orderbook_path if orderbook_path.exists() else None,
            date=run_date,
            max_candidates=max_candidates,
        )
        return output_path

    if uploaded_candidates is None:
        raise ValueError("Upload Candidate CSV terlebih dahulu.")
    config = load_hybrid_config(config_path)
    candidates = pd.read_csv(uploaded_candidates)
    if uploaded_broker is not None:
        candidates = _merge_uploaded_hybrid_source(candidates, pd.read_csv(uploaded_broker))
    if uploaded_orderbook is not None:
        candidates = _merge_uploaded_hybrid_source(candidates, pd.read_csv(uploaded_orderbook))
    output = build_hybrid_watchlist(
        candidates,
        mode=mode,
        capital_profile=capital_profile,
        config=config,
        date=run_date,
        max_candidates=max_candidates,
    )
    output_root = Path(st.session_state.get("latest_hybrid_upload_dir", DEFAULT_RUN_ROOT / "hybrid_uploads"))
    output_root.mkdir(parents=True, exist_ok=True)
    output_path = output_root / f"hybrid_watchlist_{create_run_id()}.csv"
    output.to_csv(output_path, index=False)
    st.session_state["latest_hybrid_upload_dir"] = str(output_root)
    return output_path


def _merge_uploaded_hybrid_source(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    if left.empty or right.empty:
        return left
    for key in ["ticker", "symbol"]:
        if key in left.columns and key in right.columns:
            return left.merge(right, on=key, how="left", suffixes=("", f"_{key}_extra"))
    raise ValueError("CSV tambahan harus punya kolom ticker atau symbol yang sama dengan Candidate CSV.")


def _render_hybrid_watchlist_table(st: Any, df: pd.DataFrame, path: Path) -> None:
    if df.empty:
        st.warning(f"Tidak ada row hybrid di {path}")
        return
    status_counts = df["final_status"].value_counts().to_dict() if "final_status" in df.columns else {}
    cols = st.columns(5)
    cols[0].metric("Rows", len(df))
    cols[1].metric("Execution ready", status_counts.get("EXECUTION_READY", 0))
    cols[2].metric("Need orderbook", status_counts.get("NEED_ORDERBOOK", 0))
    cols[3].metric("Ready soon", status_counts.get("READY_SOON", 0))
    cols[4].metric("Early watch", status_counts.get("EARLY_WATCH", 0))

    search = st.text_input("Cari hybrid watchlist", value="", key=f"hybrid_search_{path}", help="Cari kode saham, status, warning, atau explanation.")
    filtered = _filter_table(df, search)
    filtered = _apply_bucket_filters(st, filtered, key_prefix=f"hybrid_{path.name}_{path.stat().st_mtime_ns if path.exists() else 0}")
    preferred = [
        "rank",
        "symbol",
        "name",
        "mode",
        "final_status",
        "final_score",
        "flow_source",
        "liquidity_score",
        "technical_score",
        "smart_money_score",
        "price_extension_score",
        "orderbook_score",
        "risk_plan_score",
        "net_profit_after_fee",
        "warnings",
        "skip_reasons",
        "explanation",
    ]
    visible = [column for column in preferred if column in filtered.columns]
    visible += [column for column in filtered.columns if column not in visible]
    st.dataframe(filtered[visible], use_container_width=True, hide_index=True)
    st.download_button("Download hybrid CSV", data=filtered.to_csv(index=False), file_name=path.name, mime="text/csv", key=f"hybrid_download_{path}")
    if "explanation" in filtered.columns and not filtered.empty:
        labels = [
            f"{row.get('rank', index + 1)} - {row.get('symbol', row.get('ticker', ''))} - {row.get('final_status', '')}"
            for index, row in filtered.head(50).iterrows()
        ]
        selected = st.selectbox("Lihat explanation", labels, key=f"hybrid_explanation_{path}")
        selected_index = labels.index(selected)
        st.info(str(filtered.head(50).iloc[selected_index].get("explanation", "")))


def _render_overview(st: Any, run_dir: Path | None) -> None:
    st.subheader("Overview")
    if run_dir is None:
        st.info("No UI run found yet. Run a pipeline or inspect an existing output folder.")
        return
    summary = summarize_run(run_dir)
    metrics = [
        ("Stage 1 rows", summary["stage1_rows"]),
        ("Liquid rows", summary["liquid_rows"]),
        ("Bandar watch", summary["bandar_watch"]),
        ("Valid plans", summary["valid_trade_plans"]),
        ("Hybrid rows", summary["hybrid_watch_rows"]),
        ("Exec ready", summary["hybrid_ready"]),
        ("Closed trades", summary["closed_trades"]),
        ("Win rate", _format_pct(summary["win_rate"])),
    ]
    cols = st.columns(len(metrics))
    for col, (label, value) in zip(cols, metrics):
        col.metric(label, value)
    st.caption(f"Sedang membaca folder hasil: {run_dir}")
    _render_file_status(st, run_dir)


def _render_file_status(st: Any, run_dir: Path) -> None:
    rows = []
    for label, filename in STAGE_FILES.items():
        path = resolve_artifact_path(run_dir, label)
        rows.append({"artifact": label, "exists": path.exists(), "path": str(path), "size_kb": round(path.stat().st_size / 1024, 1) if path.exists() else 0})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_results_explorer(st: Any, run_dir: Path | None) -> None:
    st.subheader("Results Explorer")
    st.caption("Gunakan halaman ini untuk mencari saham, filter status, dan download hasil analisis.")
    if run_dir is None:
        st.info("No run selected.")
        return
    artifact_map = {
        "Stage 1 Liquidity": resolve_artifact_path(run_dir, "stage1"),
        "Stage 2 Technical": resolve_artifact_path(run_dir, "stage2"),
        "Stage 3B Bandarmology": resolve_artifact_path(run_dir, "stage3b"),
        "Stage 3C Orderbook": resolve_artifact_path(run_dir, "stage3c"),
        "Stage 4 Trade Plan": resolve_artifact_path(run_dir, "stage4"),
        "Hybrid Watchlist": resolve_artifact_path(run_dir, "hybrid_watchlist"),
        "Stage 5 Trades": resolve_artifact_path(run_dir, "stage5_trades"),
        "Stage 5 BPJS Paper": resolve_artifact_path(run_dir, "stage5_bpjs_paper"),
    }
    label = st.selectbox(
        "Jenis hasil yang dibuka",
        list(artifact_map.keys()),
        help="Pilih tabel hasil. Stage 1 paling awal, Stage 4 adalah rencana trade, Stage 5 adalah simulasi/backtest.",
    )
    path = artifact_map[label]
    df = load_csv(path)
    if df.empty:
        st.warning(f"No rows found at {path}")
        return
    search = st.text_input("Cari kode saham atau teks", value="", help="Contoh: BBRI, VALID_TRADE_PLAN, BREAKOUT, atau kata lain di tabel.")
    filtered = _filter_table(df, search)
    filtered = _apply_bucket_filters(st, filtered, key_prefix="results")
    st.caption(f"{len(filtered)} of {len(df)} rows")
    st.dataframe(filtered, use_container_width=True, hide_index=True)
    st.download_button("Download filtered CSV", data=filtered.to_csv(index=False), file_name=path.name, mime="text/csv")


def _filter_table(df: pd.DataFrame, search: str) -> pd.DataFrame:
    if not search.strip():
        return df
    needle = search.strip().lower()
    text = df.astype(str).agg(" ".join, axis=1).str.lower()
    return df[text.str.contains(needle, regex=False)].copy()


def _apply_bucket_filters(st: Any, df: pd.DataFrame, key_prefix: str = "filters") -> pd.DataFrame:
    filtered = df
    for column in ["liquidity_bucket", "trade_candidate_bucket", "entry_setup", "technical_context", "bandarmology_signal", "orderbook_status", "trade_status", "backtest_status", "final_status", "flow_source", "mode", "capital_profile"]:
        if column not in filtered.columns:
            continue
        values = sorted(value for value in filtered[column].dropna().astype(str).unique() if value)
        if not values:
            continue
        selected = st.multiselect(
            FILTER_LABELS.get(column, column),
            values,
            default=values,
            help=FILTER_HELP.get(column),
            key=f"{key_prefix}_{column}",
        )
        filtered = filtered[filtered[column].astype(str).isin(selected)]
    return filtered


def _render_reports(st: Any, run_dir: Path | None) -> None:
    st.subheader("Reports")
    st.caption("Bagian ini membaca laporan Stage 6 yang sudah dibuat dari evidence pipeline.")
    if run_dir is None:
        st.info("No run selected.")
        return
    report_path = resolve_artifact_path(run_dir, "stage6_report")
    ranking_path = resolve_artifact_path(run_dir, "stage6_ranking")
    watchlist_path = resolve_artifact_path(run_dir, "stage6_watchlist")
    if report_path.exists():
        st.markdown(report_path.read_text(encoding="utf-8"))
    else:
        st.warning(f"No Stage 6 markdown report found at {report_path}")
    cols = st.columns(2)
    with cols[0]:
        st.write("Ranking dari laporan AI")
        st.json(load_json(ranking_path))
    with cols[1]:
        st.write("Catatan watchlist")
        watchlist = load_csv(watchlist_path)
        if watchlist.empty:
            st.caption("No watchlist notes CSV found.")
        else:
            st.dataframe(watchlist, use_container_width=True, hide_index=True)


def _render_cache_settings(st: Any, sidebar: dict[str, Any], run_dir: Path | None) -> None:
    st.subheader("Cache & Settings")
    st.caption("Cek lokasi database harga lokal, token API, dan file hasil run.")
    market_db = Path(sidebar["market_data_db"])
    st.metric("Database harga lokal ada?", "Ya" if market_db.exists() else "Belum")
    st.caption(str(market_db))
    if market_db.exists():
        st.write({"size_kb": round(market_db.stat().st_size / 1024, 1), "modified": datetime.fromtimestamp(market_db.stat().st_mtime).isoformat(timespec="seconds")})
    st.write("Status token API")
    st.dataframe(
        pd.DataFrame(
            [
                {"name": "STOCKBIT_TOKEN", "available": token_available("STOCKBIT_TOKEN")},
                {"name": "DEEPSEEK_API_KEY", "available": token_available("DEEPSEEK_API_KEY")},
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )
    if run_dir:
        st.write("File di run yang sedang dibaca")
        _render_file_status(st, run_dir)


def _format_pct(value: Any) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "-"


def _inject_css(st: Any) -> None:
    st.markdown(
        """
        <style>
        :root {
            --terminal-bg: #0f1412;
            --terminal-panel: #151d1a;
            --terminal-sidebar: #121916;
            --terminal-input: #1b2521;
            --terminal-border: #2b3833;
            --terminal-ink: #e7f0eb;
            --terminal-muted: #9ca9a3;
            --terminal-green: #2dd4a6;
            --terminal-red: #ff6b63;
        }
        .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"] {
            background: var(--terminal-bg) !important;
            color: var(--terminal-ink) !important;
        }
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"] {
            background: var(--terminal-bg) !important;
            color: var(--terminal-ink) !important;
        }
        [data-testid="stSidebar"],
        [data-testid="stSidebarContent"] {
            background: var(--terminal-sidebar) !important;
            border-right: 1px solid var(--terminal-border);
            color: var(--terminal-ink) !important;
        }
        h1, h2, h3, h4, h5, h6, p, span, label, div {
            letter-spacing: 0;
        }
        h1, h2, h3, h4, p, label,
        [data-testid="stMarkdownContainer"],
        [data-testid="stWidgetLabel"],
        [data-testid="stSidebar"] * {
            color: var(--terminal-ink) !important;
        }
        small, .stCaptionContainer, [data-testid="stCaptionContainer"] {
            color: var(--terminal-muted) !important;
        }
        input, textarea,
        [data-baseweb="input"],
        [data-baseweb="input"] > div,
        [data-baseweb="textarea"] textarea,
        [data-baseweb="select"],
        [data-baseweb="select"] > div,
        [data-baseweb="tag"],
        [data-baseweb="base-input"] {
            background: var(--terminal-input) !important;
            color: var(--terminal-ink) !important;
            border-color: #3a4a44 !important;
            caret-color: var(--terminal-ink) !important;
        }
        input::placeholder, textarea::placeholder {
            color: #74827b !important;
        }
        [data-baseweb="tag"] {
            background: #20473d !important;
            color: #d9fff3 !important;
            border-radius: 6px !important;
        }
        [data-baseweb="tag"] span,
        [data-baseweb="tag"] svg {
            color: #d9fff3 !important;
            fill: #d9fff3 !important;
        }
        [role="tab"] {
            color: var(--terminal-muted) !important;
        }
        [role="tab"][aria-selected="true"] {
            color: var(--terminal-green) !important;
            border-bottom-color: var(--terminal-green) !important;
        }
        div[data-testid="stMetric"] {
            background: var(--terminal-panel);
            border: 1px solid var(--terminal-border);
            border-radius: 8px;
            padding: 10px 12px;
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--terminal-border);
            border-radius: 8px;
        }
        .stButton > button {
            border-radius: 8px;
            border: 1px solid #269b7e;
            background: var(--terminal-green);
            color: #07110e;
            font-weight: 600;
        }
        .stButton > button:hover {
            border-color: #6df0cd;
            background: #6df0cd;
            color: #07110e;
        }
        [data-testid="stFileUploader"] section {
            background: var(--terminal-input) !important;
            border-color: #3a4a44 !important;
        }
        [data-testid="stFileUploader"] button {
            background: #22312c !important;
            color: var(--terminal-ink) !important;
            border-color: #3a4a44 !important;
        }
        [data-testid="stExpander"] {
            background: var(--terminal-panel) !important;
            border: 1px solid var(--terminal-border) !important;
            border-radius: 8px !important;
        }
        [data-testid="stAlert"] {
            background: #18231f !important;
            color: var(--terminal-ink) !important;
            border-color: var(--terminal-border) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
