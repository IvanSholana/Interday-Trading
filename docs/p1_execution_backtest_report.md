# Laporan Implementasi P1 - Execution, Portfolio, dan Walk-Forward

Tanggal: 2026-07-10

## Ringkasan hasil

P1 diimplementasikan sebagai lapisan baru yang kompatibel dengan modul replay lama. Perubahan ini memengaruhi execution/risk decisions dan evaluasi backtest; tidak ada perubahan frontend.

## Implementasi

| Area | File | Perubahan |
|---|---|---|
| Portfolio accounting | `portfolio/ledger.py` | Available/reserved cash, single open position, pending order, realized/unrealized PnL, gross exposure, peak equity, floating drawdown, daily loss, dan mark-to-market snapshots. |
| Order contract | `execution/orders.py` | Planned vs actual entry/lots, order type, stop/target, risk budget, broker/orderbook snapshot timestamp. |
| Fill model | `execution/fill_model.py` | Next-open, limit buy, stop-entry breakout, trigger validation, actual-fill risk recalculation, suspension, ARA/ARB non-fill, liquidity capacity, dan partial fill. |
| Exit simulation | `backtest/simulator.py` | Gap-through-stop dieksekusi pada open yang lebih buruk; same-bar TP/SL tetap konservatif. |
| Cost model | `backtest/config.py`, `backtest/cost_model.py` | Fee beli, fee jual, pajak jual, spread, dan slippage dapat dicatat terpisah. |
| Signal replay | `backtest/signal_replay.py` | Legacy Stage-4/CSV backtest diberi nama eksplisit `SignalReplayBacktester`. |
| Walk-forward | `backtest/walk_forward.py`, `backtest/bpjs_pipeline.py` | `WalkForwardPipelineBacktester` memotong input per decision timestamp dan memakai evaluator BPJS konkret untuk menghitung ulang technical setup, optional snapshot overlay, ranking, trade plan, order/fill, dan ledger. |
| Point-in-time stores | `point_in_time_market_store.py`, `universe_history_store.py`, `corporate_action_store.py` | OHLCV cutoff facade, universe membership `valid_from/valid_to`, serta persistent corporate-action query berdasarkan announcement timestamp. |
| Reproducibility | `experiments/manifest.py` | Config hash deterministik, seed, feature/strategy version, universe/data version, commit hash, dan artifact path. |
| Market regime | `hybrid_screener.py` | IHSG-only fallback dilabeli `ihsg_trend_regime` / `IHSG_TREND_FALLBACK`; breadth yang hilang menurunkan coverage. |

## Invariant dan kebijakan

- `max_input_timestamp <= data_cutoff_timestamp <= decision_timestamp` divalidasi sebelum evaluator menerima snapshot.
- Hanya satu primary order diproses per decision date dan posisi kedua ditolak selama posisi sebelumnya masih terbuka.
- Reserved cash tidak dapat digunakan kembali sebelum order dibatalkan atau diisi.
- Actual fill yang lebih buruk menghitung ulang actual risk dan dibatalkan bila melewati max risk.
- Stop gap memakai harga open bila open berada di bawah planned stop.
- Bila TP dan SL tersentuh pada bar yang sama, stop dipilih secara konservatif.
- Static universe tetap didukung, tetapi manifest menandainya `STATIC_UNIVERSE_SURVIVORSHIP_RISK`; caller dapat memberikan point-in-time universe provider.

## Test result

- Focused P1/backtest: `79 passed`.
- Full repository: `498 passed`, `1 warning`.
- Warning: deprecation dari FastAPI/Starlette test client terhadap versi `httpx` lama.
- `compileall` lulus.

Test baru meliputi insufficient cash, second-position rejection, mark-to-market equity, gap stop, same-bar ambiguity, limit non-trigger, breakout trigger, post-fill risk, ARA/ARB non-fill, partial fill, cost breakdown, deterministic walk-forward, future-data invariance, dan snapshot timestamp guard.

## Remaining risks

### Fixed

- Tidak ada portfolio cash ledger dan floating drawdown.
- Planned entry dianggap sama dengan actual fill.
- Stop gap selalu diasumsikan terisi pada stop.
- Tidak ada partial/non-fill atau post-fill risk cancellation.
- Legacy signal replay dapat disalahartikan sebagai end-to-end pipeline backtest.

### Partially fixed

- Evaluator BPJS konkret tersedia sebagai default. Validitas riset tetap bergantung pada historical broker/orderbook providers yang memiliki timestamp dan coverage nyata.
- Universe provider as-of didukung, tetapi repository belum memiliki universe-history dataset lengkap.
- Broker/orderbook timestamp guard tersedia, tetapi historical snapshots belum tersedia untuk backtest panjang.

### Membutuhkan historical data / paper trading

- Point-in-time IDX universe dan delisting history.
- Broker-flow dan orderbook snapshots historis dengan coverage terukur.
- Empirical fill/partial-fill/slippage calibration.
- Ablation dan robustness study terhadap seluruh optional filter.
- Forward paper-trading validation minimal sebelum live capital.

## Acceptance status

`P0_COMPLETE_P1_NOT_COMPLETE`

P0 code path sudah lengkap, termasuk persistent corporate-action as-of integration dan default BPJS pada core pipeline/CLI. P1 execution, accounting, universe provider, dan concrete walk-forward evaluator sudah tersedia; P1 belum dinyatakan complete karena repository belum berisi historical universe/broker/orderbook datasets dengan coverage yang cukup. Sistem belum `PAPER_TRADING_READY`.
