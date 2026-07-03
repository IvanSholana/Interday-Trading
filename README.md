# IDX Liquidity Screener

Project Python kecil untuk screening likuiditas saham IDX sebagai tahap pertama workflow interday trading. Data harga dan volume diambil dari Yahoo Finance melalui `yfinance`, lalu nilai transaksi diproksikan sebagai `Close * Volume`.

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Cara Pakai

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

Stage 3A - broker summary collector dari Stockbit untuk shortlist Stage 2:

```powershell
python main.py stage3a `
  --input data\output\stage2_technical_context.csv `
  --output data\output\stage3a_broker_summary_raw.csv `
  --raw-dir data\raw_stockbit `
  --from-date 2026-06-01 `
  --to-date 2026-06-19 `
  --limit 25 `
  --sleep-seconds 3
```

Stage 3B - bandarmology scoring:

```powershell
python main.py stage3b `
  --stage2 data\output\stage2_technical_context.csv `
  --detector-summary data\output\stage3a_bandar_detector_summary.csv `
  --broker-summary data\output\stage3a_broker_summary_long.csv `
  --output data\output\stage3b_bandarmology_score.csv
```

Stage 4 - final trade plan dan risk management:

```powershell
python main.py stage4 `
  --stage2 data\output\stage2_technical_context.csv `
  --bandarmology data\output\stage3b_bandarmology_score.csv `
  --output data\output\stage4_trade_plan.csv `
  --capital 10000000 `
  --risk-per-trade-pct 0.005 `
  --max-position-pct 0.20
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

Bucket likuiditas:

- `LIQUID`: lolos threshold nilai transaksi rata-rata, median, nilai terakhir, hari aktif, volume ratio, dan return 5 hari tidak terlalu ekstrem.
- `WATCH`: cukup layak dipantau, tetapi belum konsisten penuh.
- `THIN`: data tersedia namun likuiditas tipis atau tidak stabil.
- `ILLIQUID`: nilai transaksi rendah atau terlalu banyak hari volume nol.
- `NO_DATA`: data kosong atau gagal diunduh.

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

Stage 3A mengambil broker summary dari Stockbit untuk ticker dengan `bandar_watch_eligible = True`. Token dibaca dari `.env` sebagai `STOCKBIT_TOKEN`; jangan hardcode token dan jangan commit `.env`.

Stage 3B menghitung `bandarmology_score` dan `bandarmology_signal` dari broker summary.

Stage 4 membuat trade plan final hanya jika Stage 2 dan Stage 3B sama-sama mendukung. Default-nya Stage 4 membutuhkan broker confirmation; gunakan `--allow-trade-without-broker-data` hanya untuk mode eksplorasi.

Stage 5 backtesting belum diimplementasikan.

## Stage 4 Trade Plan

Output utama:

- `trade_status`: `VALID_TRADE_PLAN`, `SKIPPED_NOT_TRADE_CANDIDATE`, `INVALID_DATA`, status `WAIT_*`, atau status `REJECT_*`
- `entry_trigger_price`, `entry_price`, `entry_zone_low`, `entry_zone_high`
- `stop_loss`, `stop_loss_pct`
- `take_profit_1` dan `take_profit_2`, default 5% dan 8%
- `risk_reward_tp1`, `risk_reward_tp2`
- `theoretical_position_size_lots` untuk analisis
- `executable_position_size_lots` dan `position_size_lots` hanya terisi lebih dari 0 jika `is_plan_valid = True`

Stage 4 memakai parameter modal dan risiko dari CLI. Default-nya: modal 10 juta, risiko 0.5% per rencana, maksimum risiko 1%, maksimum posisi 20% modal, max stop 6%, dan lot size 100 saham. Trade yang reject/wait/skip tidak pernah menampilkan lot eksekusi aktif.

Harga Stage 3 dibulatkan ke fraksi harga BEI sebelum validasi final:

- `< 200`: tick 1
- `200-499`: tick 2
- `500-1.999`: tick 5
- `2.000-4.999`: tick 10
- `>= 5.000`: tick 25

CSV menyimpan harga raw dan harga final rounded. Risk/reward, stop risk, dan position sizing selalu dihitung ulang dari harga final yang sudah valid tick.

## Safety

Ini bukan rekomendasi investasi. Gunakan hanya data yang kamu berhak akses, hormati rate limit dan Terms of Service platform data, jangan hardcode token, dan jangan gunakan output ini untuk auto order.
