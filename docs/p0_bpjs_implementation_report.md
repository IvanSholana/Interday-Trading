# Laporan Implementasi Fondasi P0 BPJS

Tanggal: 2026-07-10

## Baseline

- Branch: `master`
- Commit awal: `79a22d32d2cf182b2ba53238e4c944de74141db2`
- Worktree awal: hanya `.claude/` untracked; tidak diubah.
- Perintah test standar gagal sebelum collection karena `.venv` masih menunjuk ke Python 3.10 yang tidak tersedia.
- Baseline collection dengan Python 3.12 bundel awalnya gagal pada binary `pydantic_core` dari environment Python 3.10. Test akhirnya dapat dijalankan dengan preloading dependency binary dari runtime bundel.

## Implementation plan dan hasil

| Prioritas | File / area | Hasil |
|---|---|---|
| P0.1 | `bpjs_config.py`, `hybrid_config.py`, `trade_plan.py`, `config/screener.yml` | Profil BPJS terpusat untuk modal, satu posisi, risiko, stop, TP, holding period, biaya, pajak, slippage, dan lot size. |
| P0.2 | `position_sizing.py`, `hybrid_screener.py` | Final size memakai batas cash, capital, risk, dan optional liquidity; seluruh angka direkonsiliasi setelah pembulatan lot. |
| P0.3-P0.4 | `constants.py`, `hybrid_screener.py` | Ditambahkan funnel canonical, caps per funnel, primary candidate, daily `NO_TRADE`, data coverage, missing-feature policy, dan confidence. Commodity/broker/extension context tidak lagi otomatis menjadi hard reject. |
| P0.5 | `hybrid_config.py`, `hybrid_screener.py`, `recommendation.py` | Expected net return menghitung buy fee, sell fee, sell tax, spread, dan slippage; net R:R menjadi execution gate. |
| P0.6 | `technical.py`, `metrics.py`, `point_in_time.py` | Baseline rolling volume/value/high/low menggunakan prior rows dan invariant menolak future rows. |
| P0.7 | `adjusted_price.py`, `technical.py` | Raw dan adjusted OHLCV dipisahkan; indikator memakai adjusted series dan trade planning menerima raw close. |
| P0.8 | `corporate_action_store.py`, `hybrid_screener.py` | Event store mendukung query as-of berdasarkan announcement timestamp; inferensi blackout dari rasio adjusted/raw dihapus. |

## Perubahan perilaku penting

- BPJS default memakai maksimum 100% modal karena hanya satu posisi, tetapi tetap dibatasi stop risk, cash after cost, dan liquidity participation.
- Risk budget default menjadi 1%, max risk 1.5%, hard max loss 2%, stop default 1% (maksimum 1.5%), TP 2%/3%, holding maksimum 3 sesi.
- Satu lot ditolak jika cash atau actual stop risk melampaui batas.
- `enable_liquidity_sizer=True` sekarang mengubah `config.liquidity_sizer.enabled`, bukan hanya threshold.
- Status granular lama dipertahankan untuk kompatibilitas. Kolom `funnel_status` menyediakan `WATCHLIST`, `READY_SOON`, `EXECUTION_READY`, atau `REJECT`; `daily_decision` menjadi `NO_TRADE` bila tidak ada kandidat execution-ready.
- Missing optional data menurunkan coverage/confidence dan ranking, tetapi tidak otomatis menolak kandidat.
- Sideways compression dan trigger yang secara eksplisit belum tersentuh tidak dapat menjadi execution-ready.

## Test result

- Focused P0/trading tests: `107 passed`.
- Full repository suite: `477 passed`, `1 warning`.
- Warning tersisa berasal dari deprecation `fastapi.testclient`/Starlette terhadap package `httpx` lama.
- Syntax validation: `python -m compileall -q src tests` lulus.
- Git whitespace validation: `git diff --check` lulus.

## Remaining risks

### Fixed

- Liquidity toggle tidak mengaktifkan fitur.
- Position sizing hanya capital-based saat liquidity sizer mati.
- Sell tax tidak dipisahkan dari broker fee.
- Rolling reference memasukkan decision bar.
- Adjusted/raw price belum dipisahkan lengkap.
- Corporate-action dates diinferensikan dengan hindsight dari adjustment ratio.

### Partially fixed

- Single source of truth sudah dipakai hybrid dan trade-plan core, tetapi beberapa CLI/API legacy masih mengekspos default interday eksplisit.
- Corporate-action store tersedia dan leakage inference sudah dihapus, tetapi ingestion source yang timestamped belum tersedia.
- Funnel harian tersedia di output hybrid, sementara downstream reports lama masih memakai granular status.

### Unresolved / membutuhkan historical data

- Point-in-time universe history dan survivorship-bias-safe universe.
- Historical broker/orderbook snapshots dengan timestamp dan coverage yang cukup.
- Walk-forward pipeline backtester end-to-end yang menghitung ulang seluruh stage per cutoff.
- Ablation study untuk broker flow, orderbook, commodity, regime, dan multibar confirmation.
- Empirical calibration threshold; unit test bukan bukti profitabilitas.

### Membutuhkan paper trading

- Fill rate, partial fills, ARA/ARB non-fill frequency, gap loss, dan realized slippage.
- Validasi minimal beberapa minggu/siklus pasar sebelum keputusan live.

## Acceptance status

`P0_NOT_COMPLETE`

Alasan: fondasi P0 utama dan guard leakage telah diimplementasikan, tetapi corporate-action ingestion point-in-time dan seluruh default legacy interface belum sepenuhnya tersatukan. P1 walk-forward accounting juga belum selesai, sehingga repository belum layak disebut `PAPER_TRADING_READY`.
