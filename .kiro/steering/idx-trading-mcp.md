---
inclusion: auto
---


# IDX Interday Trading MCP — Agent Operating Guide
You have access to an IDX interday trading MCP server with 29 tools. This guide defines when and how to use them optimally.

## Context Awareness

Before any action, determine:
1. **Day type**: weekday (market open) or weekend (market closed)
2. **Time of day**: before market (pre-9AM WIB), during market (9AM-4PM), after market (post-4PM)
3. **User intent**: analysis, execution planning, review, or parameter exploration

## Tool Selection Matrix

### User wants: "Analisis saham / rekomendasi hari ini"
```
1. get_system_health → confirm OK
2. get_dividend_calendar → check ex-date blackout (JANGAN rekomendasikan saham ex-date!)
3. scan_bandar_activity → identify smart money accumulation (broker flow)
4. get_insider_activity(7) → identify insider buy signals (directors/owners)
5. run_trading_pipeline OR start_pipeline_run → run scan
6. diagnose_run → understand results in 1 call
7. suggest_next_action → what to do next
8. IF valid plans exist: get_run_bundle → full review
9. IF 0 plans: what_if(capital=higher) → show alternatives
```

### User wants: "Smart money / bandar lagi akumulasi apa?"
```
1. scan_bandar_activity(period="RT_PERIOD_LAST_7_DAYS", investor_type="INVESTOR_TYPE_FOREIGN") → broker asing
2. scan_bandar_activity(period="RT_PERIOD_LAST_1_DAY", investor_type="INVESTOR_TYPE_DOMESTIC") → broker lokal
3. get_insider_activity(7) → insider (direksi/pemilik) beli/jual
4. Cross-reference: saham yang muncul di KEDUA list = highest conviction
```

### User wants: "Sentimen pasar / berita / katalis"
```
Gunakan web_search (BUKAN MCP tool) untuk:
1. Search "IDX IHSG sentimen [bulan] [tahun]" → arah pasar
2. Search "[ticker] berita terbaru [tahun]" → katalis spesifik
3. Search "saham Indonesia rekomendasi analis [bulan]" → konsensus broker
4. Search "komoditas [emas/CPO/batubara] harga terbaru" → sektor driver

Lalu cross-reference dengan MCP tools:
- Saham dari berita positif → cek scan_bandar_activity (apakah smart money juga masuk?)
- Saham dari rekomendasi analis → cek get_insider_activity (apakah insider confirm?)
- Sektor yang katalisnya kuat → jalankan pipeline dengan ticker sektor itu
- WAJIB cek get_dividend_calendar → jangan rekomendasikan saham ex-date!

PENTING: Web search = sentimen/narasi. MCP tools = data kuantitatif.
Keduanya harus ALIGN sebelum rekomendasi. Jika sentimen bullish tapi smart money tidak masuk → HATI-HATI.
```

### User wants: "Dividen / cum-date / ex-date"
```
1. get_dividend_calendar → semua upcoming events + yield + dates
2. Saham ex-date HARI INI → JANGAN BELI (harga pasti turun)
3. Saham cum-date mendekati + yield > 2% → potensial cum-date play
4. Cross-reference dengan get_insider_activity → insider beli sebelum cum = strong signal
```

### User wants: "Cek saham X" (specific ticker)
```
1. get_dividend_calendar → check if ticker is near ex-date (DANGER if yes)
2. get_ticker_stage_details(run_id, ticker) → full stage breakdown
3. get_intraday_analysis(ticker) → VWAP + gap (if weekday)
4. get_foreign_flow(ticker, 5) → institutional interest
5. get_insider_activity → check if insider is buying
6. scan_bandar_activity → check if broker is accumulating this ticker
```

### User wants: "Pakai modal X, target Y%"
```
1. what_if(run_id, capital=X) → instant simulation, no re-run needed
2. IF no existing run: run_trading_pipeline with user params
3. get_trade_recommendation(capital=X, max_tp_pct=Y/100)
```

### User wants: "Bandingkan / evaluasi"
```
1. compare_runs(older_id, newer_id) → delta summary
2. diagnose_run on each → understand differences
```

### Rejected ticker breakout / "kenapa ga masuk X padahal naik?"
```
1. recheck_ticker(ticker, run_id) → re-evaluate with fresh intraday data
2. IF RECHECK_PASSED: show new entry plan (VWAP-based SL)
3. IF RECHECK_ARMED: monitor, call again in 15-30 min
4. IF STILL_REJECTED: original rejection valid, jangan FOMO
```

### Weekend / Market Closed
```
NEVER run pipeline (no new data).
USE: list_pipeline_runs → diagnose_run → what_if → suggest_next_action
```

## Tool Priorities (call these FIRST)

| Situation | First tool | Why |
|-----------|-----------|-----|
| After ANY run | `diagnose_run` | 1 call = full explanation (vs 5+ inspection tools) |
| Before ANY buy recommendation | `get_dividend_calendar` | NEVER recommend a stock on ex-date |
| Before recommending | `scan_bandar_activity` + `get_insider_activity` | Smart money + insider = strongest confirmation |
| 0 valid plans | `what_if` + `suggest_next_action` | Don't just say "gagal" — show alternatives |
| User asks "kenapa" | `diagnose_run` | Never manually inspect stage-by-stage |
| User asks "smart money" | `scan_bandar_activity` | Broker accumulation list |
| User asks "insider" | `get_insider_activity` | Directors/owners buying |
| User asks "dividen" | `get_dividend_calendar` | Ex-date danger + cum-date plays |

## Tools to AVOID calling unnecessarily

- `get_run_details` → use `diagnose_run` instead (more insightful)
- `get_ticker_stage_details` for ALL tickers → use `diagnose_run` for summary first
- `run_trading_pipeline` on weekends → will waste time, no new data
- `refresh_market_data_stockbit` if data already cached today → check `get_system_health` first

## Parameter Defaults

When user doesn't specify:
- `capital`: Rp500,000 (small retail)
- `risk_per_trade_pct`: 0.02 (2% — appropriate for small capital)
- `max_position_pct`: 0.80 (80% — allows concentrated positions for small accounts)
- `universe_key`: "lq45" for quick scans, "idx80" for broader
- `run_phase`: "malam" for evening analysis, "pagi" for morning confirmation

## Response Pattern

Always structure your response to the user as:

1. **Situasi** — 1 sentence on market/data state
2. **Temuan** — Key findings from tools (insider, watchlist, scores)
3. **Rekomendasi** — Specific actionable guidance
4. **Catatan risiko** — Caveats (this is decision support, not order instruction)

### CRITICAL: Presentation Rules by Status

- **EXECUTION_READY / EXECUTION_DRAFT**: Show full trade plan (entry, TP, SL, lots, R:R)
- **NEED_ORDERBOOK**: Show plan but prefix with "⚠️ Belum dikonfirmasi orderbook"
- **EARLY_WATCH / WATCH_ONLY**: **JANGAN tampilkan angka entry/TP/SL sebagai trade plan.** Cukup bilang:
  - "Pantau di area Rp[X]-Rp[Y]"
  - "Entry hanya jika [kondisi] terpenuhi"
  - "Belum layak trade — status hanya WATCH"
- **SKIP / REJECT**: Bilang "Ditolak karena [alasan]". Tidak perlu tampilkan angka.

**ALASAN**: Menampilkan entry/TP/SL untuk kandidat WATCH membuat user mengira itu trade plan operasional. Ini yang menyebabkan kerugian MEDC — plan ditampilkan padahal status hanya WATCH.

## Anti-patterns to AVOID

- ❌ Running pipeline then only showing "0 valid plans" without explanation
- ❌ Calling 5+ inspection tools when `diagnose_run` answers the question
- ❌ Suggesting trades without checking insider activity and foreign flow
- ❌ **Recommending a stock on or near ex-date (guaranteed loss from dividend drop)**
- ❌ Re-running pipeline with same params expecting different results
- ❌ Ignoring `suggest_next_action` output
- ❌ Forgetting to mention capital constraints when plans are rejected for sizing
- ❌ Not checking `get_dividend_calendar` before any buy recommendation
- ❌ **Ignoring 401 errors — always call `validate_token` first, then tell user to refresh**

## Workflow: Fase Malam (Evening Scan)

```
web_search "IHSG sentimen [hari ini]" → market context + sektor katalis
get_system_health
get_dividend_calendar → identify ex-date blackout tickers for tomorrow
scan_bandar_activity(period="RT_PERIOD_LAST_7_DAYS") → smart money overview
get_insider_activity(7) → insider confirmations
start_pipeline_run(universe_key, capital, run_phase="malam")
get_pipeline_run_status(job_id) [poll until done]
diagnose_run(run_id)
IF has candidates: get_run_bundle(run_id)
suggest_next_action(run_id)
Cross-reference: watchlist candidates vs web search sentiment → final conviction
VERIFY: none of the recommended tickers are on tomorrow's ex-date list
```

## Workflow: Fase Pagi (Morning Confirmation)

```
get_system_health
get_intraday_analysis(primary_ticker)
run_morning_confirmation(resume_run_id)
get_trade_recommendation(run_id)
get_foreign_flow(top_tickers, 5)
```

## Data Freshness Rules

- Pipeline uses Stockbit as primary data source (cached in sqlite)
- On weekdays after 4:30PM WIB: data is fresh (auto-updated)
- On weekends: data is Friday's close — don't re-fetch
- Insider data: cached daily, 1 API call per day max
- Intraday (VWAP/gap): only available on market days, last ~7 days

## Important Constraints

- Minimum 1 lot = 100 shares. Modal Rp500k can only buy stocks < Rp500/share at max position.
- risk_per_trade_pct is capped at max_risk_per_trade_pct (1% for interday mode).
- IDX tick sizes: Rp1 (0-200), Rp2 (200-500), Rp5 (500-2000), Rp10 (2000-5000), Rp25 (5000+)
- Trailing stop activates at +2% profit, trails 1.5% below highest. TP decays after day 3.
- Sector guard: max 2 tickers from same sector in shortlist.
