# IDX Liquidity Screener

Project Python kecil untuk screening likuiditas saham IDX sebagai tahap pertama workflow interday trading. Data harga dan volume diambil dari Yahoo Finance melalui `yfinance`, lalu nilai transaksi diproksikan sebagai `Close * Volume`.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Cara Pakai

Dashboard lokal:

```powershell
python -m streamlit run src\interday_liquidity_screener\web_app.py
```

Panduan penggunaan dashboard yang lebih santai dan langkah demi langkah tersedia di [GUIDEBOOK_DASHBOARD.md](GUIDEBOOK_DASHBOARD.md).

Dashboard mendukung mode daftar saham dari file lokal di `data/input/universes`, termasuk semua IDX, saham syariah, LQ45, IDX30, IDX80, JII, Kompas100, SRI-KEHATI, Bisnis-27, dan PEFINDO25. Update file preset tersebut saat konstituen indeks berubah.

Atau setelah package ter-install:

```powershell
interday-dashboard
```

Stage 1 - screening likuiditas:

```powershell
liquidity-screen --tickers-file examples/tickers.txt --output results/liquidity_screen_result.csv
```

Atau lewat `main.py`:

```powershell
python main.py stage1 --tickers-file examples\tickers.txt --output results\screening_stage_1_liquidity.csv
```

Stage 2 - broad technical context dari hasil stage 1:

```powershell
python main.py stage2 --input data\output\stage1_liquidity.csv --output data\output\stage2_technical_context.csv --period 1y
```

Stage 1, Stage 2, dan Stage 5 memakai database lokal SQLite untuk OHLCV Yahoo Finance di `data\cache\market_data.sqlite`. Saat run berikutnya, tool membaca histori yang sudah ada dan hanya menarik data setelah tanggal terakhir yang tersimpan. Kalau periode yang diminta lebih panjang dari isi cache, misalnya Stage 2 minta `1y` setelah Stage 1 hanya mengisi `3mo`, cache akan dilengkapi ulang untuk cakupan yang dibutuhkan.

Gunakan opsi ini bila ingin lokasi DB khusus atau force refresh:

```powershell
python main.py stage1 `
  --tickers-file examples\tickers.txt `
  --market-data-db data\cache\market_data.sqlite `
  --refresh-market-data
```

Stage 3A - broker summary collector dari Stockbit untuk shortlist Stage 2.

Mode multi-window default untuk bandarmology 1D/3D/5D/10D/20D:

```powershell
python main.py stage3a `
  --input data\output\stage2_technical_context.csv `
  --output-dir data\output\stockbit `
  --raw-dir data\raw_stockbit `
  --as-of-date 2026-07-02 `
  --windows "1D,3D,5D,10D,20D" `
  --limit 25 `
  --sleep-seconds 3
```

Mode single-window lama tetap didukung sebagai `CUSTOM` window:

```powershell
python main.py stage3a `
  --input data\output\stage2_technical_context.csv `
  --output data\output\stage3a_broker_summary_long.csv `
  --raw-dir data\raw_stockbit `
  --from-date 2026-06-01 `
  --to-date 2026-07-02 `
  --limit 25 `
  --sleep-seconds 3
```

Stage 3B - bandarmology scoring:

```powershell
python main.py stage3b `
  --stage2 data\output\stage2_technical_context.csv `
  --detector-summary data\output\stockbit\stage3a_bandar_detector_summary.csv `
  --broker-summary data\output\stockbit\stage3a_broker_summary_long.csv `
  --output data\output\stage3b_bandarmology_score.csv
```

Stage 3C - orderbook / execution quality filter dari Stockbit.

Stage ini memakai snapshot orderbook live/intraday saat command dijalankan. Ini bukan sumber backtest historis kecuali kamu menyimpan snapshot berkala.

```powershell
python main.py stage3c `
  --stage2 data\output\stage2_technical_context.csv `
  --bandarmology data\output\stage3b_bandarmology_score.csv `
  --output data\output\stage3c_orderbook_filter.csv `
  --raw-dir data\raw_stockbit_orderbook `
  --sleep-seconds 2 `
  --max-retries 3
```

Stage 4 - final trade plan dan risk management:

```powershell
python main.py stage4 `
  --stage2 data\output\stage2_technical_context.csv `
  --bandarmology data\output\stage3b_bandarmology_score.csv `
  --output data\output\stage4_trade_plan.csv `
  --strategy-mode interday `
  --capital 10000000 `
  --risk-per-trade-pct 0.005 `
  --max-position-pct 0.20
```

Stage 4 dengan orderbook optional:

```powershell
python main.py stage4 `
  --stage2 data\output\stage2_technical_context.csv `
  --bandarmology data\output\stage3b_bandarmology_score.csv `
  --orderbook data\output\stage3c_orderbook_filter.csv `
  --output data\output\stage4_trade_plan.csv `
  --capital 10000000 `
  --risk-per-trade-pct 0.005
```

Default Stage 4 adalah `--strategy-mode interday`: TP1 5%, TP2 8%, time stop 10 hari, dan orderbook hanya menjadi catatan kualitas eksekusi. Orderbook tidak otomatis menggugurkan trade plan kecuali kamu menambahkan `--require-orderbook-confirmation`.

Mode BPJS lebih ketat untuk eksekusi cepat: TP1 2%, TP2 3%, max stop default 1.5%, force exit same day, dan orderbook wajib supportive atau neutral.

```powershell
python main.py stage4 `
  --stage2 data\output\stage2_technical_context.csv `
  --bandarmology data\output\stage3b_bandarmology_score.csv `
  --orderbook data\output\stage3c_orderbook_filter.csv `
  --output data\output\stage4_trade_plan_bpjs.csv `
  --strategy-mode bpjs `
  --capital 10000000 `
  --risk-per-trade-pct 0.005
```

Jika ingin orderbook menjadi gate wajib di mode interday:

```powershell
python main.py stage4 `
  --stage2 data\output\stage2_technical_context.csv `
  --bandarmology data\output\stage3b_bandarmology_score.csv `
  --orderbook data\output\stage3c_orderbook_filter.csv `
  --output data\output\stage4_trade_plan.csv `
  --strategy-mode interday `
  --require-orderbook-confirmation
```

Stage 5A - interday backtest dari output Stage 4:

```powershell
python main.py stage5-backtest-interday `
  --signals data\output\stage4_trade_plan.csv `
  --output data\output\stage5_interday_trades.csv `
  --metrics-output data\output\stage5_interday_metrics.json `
  --equity-output data\output\stage5_interday_equity_curve.csv `
  --price-cache-dir data\cache\ohlcv `
  --market-data-db data\cache\market_data.sqlite `
  --period 1y `
  --entry-mode next_open `
  --time-stop-days 10 `
  --buy-fee-pct 0.0015 `
  --sell-fee-pct 0.0025 `
  --slippage-pct 0.001 `
  --same-day-ambiguous-policy stop_first `
  --initial-capital 10000000
```

Stage 5B - BPJS paper trading journal:

```powershell
python main.py stage5-paper-bpjs `
  --stage4 data\output\stage4_trade_plan_bpjs.csv `
  --orderbook data\output\stage3c_orderbook_filter.csv `
  --output data\output\stage5_bpjs_paper_trades.csv `
  --summary-output data\output\stage5_bpjs_daily_summary.json `
  --date 2026-07-03 `
  --entry-time 09:15 `
  --exit-time 15:45
```

Update BPJS paper journal dengan exit aktual manual:

```powershell
python main.py stage5-update-bpjs-paper `
  --paper data\output\stage5_bpjs_paper_trades.csv `
  --actual-exit data\input\bpjs_actual_exit_2026-07-03.csv `
  --output data\output\stage5_bpjs_paper_trades_updated.csv `
  --summary-output data\output\stage5_bpjs_daily_summary_updated.json
```

Stage 6 - LLM analyst review dari hasil Stage 1-5:

```powershell
python main.py stage6-build-evidence `
  --stage2 data\output\stage2_technical_context.csv `
  --bandarmology data\output\stage3b_bandarmology_score.csv `
  --orderbook data\output\stage3c_orderbook_filter.csv `
  --stage4 data\output\stage4_trade_plan.csv `
  --backtest-metrics data\output\stage5_interday_metrics.json `
  --bpjs-summary data\output\stage5_bpjs_daily_summary.json `
  --output data\output\stage6_evidence_pack.json `
  --strategy-mode interday `
  --run-date 2026-07-03 `
  --max-candidates 30
```

Generate report tanpa memanggil DeepSeek API:

```powershell
python main.py stage6-llm-report `
  --evidence data\output\stage6_evidence_pack.json `
  --report-output data\output\stage6_llm_daily_report.md `
  --ranking-output data\output\stage6_llm_candidate_ranking.json `
  --watchlist-output data\output\stage6_llm_watchlist_notes.csv `
  --raw-output data\output\stage6_llm_raw_response.json `
  --strategy-mode interday `
  --dry-run
```

Command gabungan:

```powershell
python main.py stage6 `
  --stage2 data\output\stage2_technical_context.csv `
  --bandarmology data\output\stage3b_bandarmology_score.csv `
  --orderbook data\output\stage3c_orderbook_filter.csv `
  --stage4 data\output\stage4_trade_plan.csv `
  --backtest-metrics data\output\stage5_interday_metrics.json `
  --bpjs-summary data\output\stage5_bpjs_daily_summary.json `
  --evidence-output data\output\stage6_evidence_pack.json `
  --report-output data\output\stage6_llm_daily_report.md `
  --ranking-output data\output\stage6_llm_candidate_ranking.json `
  --watchlist-output data\output\stage6_llm_watchlist_notes.csv `
  --raw-output data\output\stage6_llm_raw_response.json `
  --strategy-mode interday `
  --run-date 2026-07-03 `
  --max-candidates 30 `
  --dry-run
```

Contoh dengan threshold lebih ketat:

```powershell
liquidity-screen `
  --tickers-file examples/tickers.txt `
  --output results/liquidity_screen_result.csv `
  --min-value 7000000000 `
  --min-avg-value-20d 7000000000 `
  --min-median-value-20d 4000000000 `
  --min-active-days-20d 18
```

## Input Ticker

File input bisa `.txt` atau `.csv`.

TXT:

```text
BBCA
BMRI
TLKM.JK
```

CSV:

```csv
ticker
BBCA
BMRI
TLKM
```

Ticker akan otomatis dinormalisasi menjadi format Yahoo Finance IDX, misalnya `BBCA` menjadi `BBCA.JK`.

## Metode Screening

Stage 1 menghasilkan dua penilaian berbeda:

**Liquidity bucket** = kualitas likuiditas absolut 20 hari, independen dari setup harian:

- `HIGH_LIQUIDITY`: likuiditas sangat tinggi dan konsisten.
- `GOOD_LIQUIDITY`: cukup likuid untuk lanjut screening.
- `MEDIUM_LIQUIDITY`: ada likuiditas, tetapi belum cukup kuat untuk pipeline utama.
- `LOW_LIQUIDITY`: likuiditas rendah.
- `ILLIQUID`: nilai transaksi rendah, tidak konsisten, atau data tidak valid.

**Trade candidate bucket** = kelayakan awal sebagai watchlist hari ini, berdasarkan likuiditas + aktivitas harian + anti-chasing filter:

- `STRONG_WATCH`: likuid, aktif hari ini, tidak over-extended — eligible masuk watchlist.
- `WATCH`: cukup menarik tetapi belum semua syarat terpenuhi.
- `AVOID_FOR_NOW`: likuiditas tidak cukup, atau gagal salah satu gate harian:
  - `min_value`: transaction value hari terakhir di bawah threshold minimum.
  - `min_volume_ratio`: volume ratio hari terakhir di bawah threshold aktivitas minimum.
  - `max_return_5d`: return 5 hari terlalu tinggi (anti-chasing, menghindari beli setelah naik banyak).
  - `min_active_days_20d`: jumlah hari aktif (volume > 0) dalam 20 sesi terakhir kurang dari threshold.
- `INVALID_DATA`: data kurang 20 hari atau tidak valid.

Dengan ini, saham bisa tetap `HIGH_LIQUIDITY` (likuid secara absolut) tetapi `AVOID_FOR_NOW` di trade candidate bucket karena value_est, volume_ratio, atau return_5d tidak memenuhi gate hari ini.

Metrik penting:

- `value_est = Close * Volume`
- `avg_value_20d`
- `median_value_20d`
- `active_days_20d`
- `zero_volume_days_20d`
- `value_consistency_ratio = median_value_20d / avg_value_20d`
- `volume_ratio = latest_volume / avg_volume_20d`

Catatan: Yahoo Finance tidak menyediakan nilai transaksi resmi IDX atau frekuensi transaksi. Karena itu, `value_est` adalah proxy, bukan data resmi bursa.

## Test

```powershell
python -m pytest
```

## Pipeline

Stage 1 membuang saham tidak likuid dan data buruk.

Stage 2 membuat broad technical watchlist. Stage ini tidak boleh terlalu sempit karena bandarmology bisa mendeteksi akumulasi sebelum chart terlihat rapi. Output pentingnya: `technical_context`, `bandar_watch_eligible`, `technical_context_reason`, dan `technical_context_summary`.

Stage 3A mengambil broker summary dari Stockbit untuk ticker dengan `bandar_watch_eligible = True`. Mode multi-window mengambil 1D, 3D, 5D, 10D, dan 20D agar Stage 3B tidak terlalu bergantung pada satu periode. Token dibaca dari `.env` sebagai `STOCKBIT_TOKEN`; jangan hardcode token dan jangan commit `.env`.

Stage 3B menghitung score per window (`score_1d`, `score_3d`, `score_5d`, `score_10d`, `score_20d`) lalu membuat `weighted_bandarmology_score` dan final `bandarmology_signal`. Sinyal khusus seperti `SHORT_TERM_ACCUMULATION_AGAINST_MEDIUM_DISTRIBUTION` dan `PULLBACK_WITH_MEDIUM_ACCUMULATION` adalah watchlist, bukan executable trade plan default.

Stage 3C mengambil snapshot orderbook live/intraday untuk memeriksa kualitas eksekusi: spread, depth imbalance, bid/offer wall, tradable flag, UMA/notation/corporate action, ARA/ARB proximity, dan foreign net ringkas.

Stage 4 membuat trade plan final hanya jika Stage 2 dan Stage 3B sama-sama mendukung. Default-nya Stage 4 memakai `strategy_mode=interday`, sehingga broker confirmation tetap wajib tetapi orderbook tidak otomatis menjadi gate. Gunakan `--allow-trade-without-broker-data` hanya untuk mode eksplorasi. Jika `--orderbook` diberikan, kolom orderbook ikut muncul di output sebagai `execution_quality_note`. Jika `--require-orderbook-confirmation` dipakai, trade plan aktif hanya lolos bila `orderbook_status` `ORDERBOOK_SUPPORTIVE` atau `ORDERBOOK_NEUTRAL`. Untuk `strategy_mode=bpjs`, orderbook confirmation aktif secara default dan risiko spread/depth/orderbook dapat menggugurkan trade.

Stage 5 adalah validation layer, bukan signal layer. Stage 5A mengevaluasi output Stage 4 interday memakai OHLCV daily: entry, TP, SL, time stop, fee, slippage, MFE/MAE, metrics JSON, dan equity curve.

Jika TP dan SL tersentuh pada candle yang sama (same-day ambiguity), backtest memakai `--same-day-ambiguous-policy` yang configurable:

- `stop_first` (default, konservatif): SL dianggap kena dulu. Exit reason = `SL_HIT_SAME_DAY_AMBIGUOUS`.
- `tp_first` (optimistis): TP dianggap kena dulu. Exit reason = `TP1_HIT_SAME_DAY_AMBIGUOUS`.
- `skip_trade`: trade ambigu tidak dihitung sebagai closed trade. Status = `AMBIGUOUS_SKIPPED`. Metrics tidak memasukkan trade ini ke win/loss.

Field `ambiguous_trade_count` di metrics JSON menunjukkan berapa banyak trade yang bergantung pada asumsi intraday ambiguity.

Stage 5B adalah BPJS forward paper trading journal. Ini bukan historical backtest akurat tanpa snapshot orderbook historis. Paper trade hanya dibuat untuk Stage 4 mode `bpjs` yang valid dan orderbook `ORDERBOOK_SUPPORTIVE` atau `ORDERBOOK_NEUTRAL`.

Stage 6 adalah LLM analyst review layer. Stage ini membaca hasil Stage 1-5, membuat evidence pack ringkas, lalu menghasilkan analyst report, candidate ranking, dan watchlist notes. Stage 6 tidak membuat sinyal baru, tidak mengubah `trade_status` Stage 4, tidak mengubah stop-loss/take-profit/position sizing, dan tidak melakukan auto order.

## Stage 4 Trade Plan

Output utama:

- `trade_status`: `VALID_TRADE_PLAN`, `SKIPPED_NOT_TRADE_CANDIDATE`, `INVALID_DATA`, status `WAIT_*`, atau status `REJECT_*`
- `entry_trigger_price`, `entry_price`, `entry_zone_low`, `entry_zone_high`
- `stop_loss`, `stop_loss_pct`
- `take_profit_1` dan `take_profit_2`, default 5% dan 8%
- `risk_reward_tp1`, `risk_reward_tp2`
- `theoretical_position_size_lots` untuk analisis
- `executable_position_size_lots` dan `position_size_lots` hanya terisi lebih dari 0 jika `is_plan_valid = True`
- `strategy_mode`, `force_exit_same_day`, dan `execution_quality_note`

Stage 4 memakai parameter modal dan risiko dari CLI/dashboard. Default dashboard: modal 500 ribu, risiko 0.5% per rencana, maksimum risiko 1%, maksimum posisi 20% modal, TP1 5%, TP2 8%, max stop 6%, time stop 10 hari, dan lot size 100 saham. Saham yang nilai 1 lot-nya melebihi batas posisi per saham akan ditolak sebagai `REJECT_POSITION_TOO_SMALL`, termasuk bila sinyalnya hanya watchlist. Default `bpjs`: TP1 2%, TP2 3%, max stop 1.5%, force exit same day, dan orderbook wajib supportive/neutral. Trade yang reject/wait/skip tidak pernah menampilkan lot eksekusi aktif.

Harga Stage 3 dibulatkan ke fraksi harga BEI sebelum validasi final:

- `< 200`: tick 1
- `200-499`: tick 2
- `500-1.999`: tick 5
- `2.000-4.999`: tick 10
- `>= 5.000`: tick 25

CSV menyimpan harga raw dan harga final rounded. Risk/reward, stop risk, dan position sizing selalu dihitung ulang dari harga final yang sudah valid tick.

## Stage 5 Validation

Stage 5A membaca `stage4_trade_plan.csv` dan hanya mengevaluasi row dengan `strategy_mode=interday`, `trade_status=VALID_TRADE_PLAN`, `is_plan_valid=True`, dan lot eksekusi lebih dari 0. Row watch/reject/invalid tidak diubah menjadi trade valid.

Output Stage 5A:

- `stage5_interday_trades.csv`: satu baris per sinyal Stage 4 dengan status backtest.
- `stage5_interday_metrics.json`: win rate, profit factor, expectancy, drawdown, TP/SL/time-stop rate, MFE/MAE.
- `stage5_interday_equity_curve.csv`: realized PnL per exit date dan drawdown.

Stage 5B membaca Stage 4 mode BPJS dan orderbook snapshot terbaru. Status awal paper trade adalah `OPEN_PAPER_TRADE`; exit aktual bisa diisi belakangan lewat `stage5-update-bpjs-paper` dengan CSV `ticker, exit_price, exit_time, exit_reason`.

## Stage 6 LLM Analyst Review

Stage 6 memakai DeepSeek API hanya jika `--dry-run` tidak dipakai. Untuk koneksi API, isi env:

```env
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-reasoner
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

Evidence pack disanitasi sebelum dikirim ke LLM. Jangan kirim token Stockbit ke LLM, jangan commit `.env`, dan jangan simpan API key di output. Jika file Stage 5 optional belum ada, Stage 6 tetap jalan dan menulis warning di evidence pack.

Output Stage 6:

- `stage6_evidence_pack.json`: ringkasan deterministic dari pipeline.
- `stage6_llm_daily_report.md`: report analyst berbasis evidence.
- `stage6_llm_candidate_ranking.json`: ranking tervalidasi guardrail.
- `stage6_llm_watchlist_notes.csv`: catatan watchlist.
- `stage6_llm_raw_response.json`: raw response yang sudah disanitasi.

## Safety

Ini bukan rekomendasi investasi. Backtest dan LLM analysis bukan jaminan profit. BPJS butuh disiplin eksekusi dan forward test. Gunakan hanya data yang kamu berhak akses, hormati rate limit dan Terms of Service platform data, jangan hardcode token/API key, dan jangan gunakan output ini untuk auto order.
