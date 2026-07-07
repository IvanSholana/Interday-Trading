# Audit: Dead/Uncomputed Fields di hybrid_screener.py

**Tanggal:** 2026-07-07  
**Scope:** Semua field di `hybrid_screener.py` yang memiliki pola fallback "unavailable_neutral_score", default konstan, atau tidak pernah dihitung dari data pipeline yang ada.

## Ringkasan

| # | Field / Score | Status | Alasan |
|---|---|---|---|
| 1 | `avg_frequency_20d` | **FIXED** | Yahoo Finance tidak menyediakan frequency (jumlah transaksi/hari). Sekarang fallback ke `frequency` live dari orderbook Stage 3C. Warning `avg_frequency_20d_missing` dihapus. |
| 2 | `market_regime_score` | **DEAD** — selalu 50 (neutral) | Module `enhancements/market_regime.py` hanya berisi docstring. Tidak ada kode yang menghitung IHSG above/below MA atau breadth. Hasilnya: `score_market_regime()` selalu return `ScoreResult(50, ("market_regime_unavailable_neutral_score",))`. |
| 3 | `sector_strength_score` | **DEAD** — selalu 50 (neutral) | Tidak ada module sector scoring di codebase. `score_sector_strength()` selalu return `ScoreResult(50, ("sector_strength_unavailable_neutral_score",))`. |
| 4 | `market_sector_score` (combined) | **DEAD** — selalu 50 | Dihitung sebagai `(market_regime_score + sector_strength_score) / 2` = `(50 + 50) / 2` = 50 konstan. |
| 5 | `frequency_live` | **PARTIALLY AVAILABLE** | Hanya terisi jika data orderbook Stage 3C tersedia (yaitu hanya emiten yang lolos filter bandarmology strong/mild accumulation). Emiten yang tidak lolos filter 3C tidak memiliki field ini. |
| 6 | `broker_net_buy_{1,3,5,10,20}d` | **DEAD** — selalu None | Hybrid screener membaca key `broker_net_buy_1d`, `broker_net_buy_3d`, dll. Tapi tidak ada code di pipeline (stage 3A/3B/3C) yang menghasilkan field dengan nama ini. Field yang ada di broker summary adalah `net_lot`/`net_value` per window, yang di-aggregate ke `bandarmology_score`, bukan ke individual `broker_net_buy_{N}d`. |
| 7 | `top3_buyer_dominance` / `top3_seller_dominance` | **PARTIALLY COMPUTED** | `calculate_broker_features()` di `bandarmology.py` menghitung `top3_buyer_value` dan `top3_seller_value`, tapi **tidak menghitung ratio** `top3_buyer_value / top3_seller_value`. Hybrid screener membaca `top3_buyer_dominance` yang tidak ada sebagai kolom output. |
| 8 | `spread_ticks` | **COMPUTED ON THE FLY** | Tidak ada di CSV output manapun. Dihitung dynamically di `build_output_row()` dari `best_bid` dan `best_offer` → OK, tidak dead. |

## Dampak pada Final Score

Karena `market_regime_score` dan `sector_strength_score` selalu 50, maka:
- Di mode `bpjs_live`: `market_sector_score` punya weight 5% → kontribusi = 2.5 points konstan
- Di mode `smart_money_first`: `market_sector_score` punya weight 10% → kontribusi = 5.0 points konstan
- Di mode `normal_execution`: `market_sector_score` punya weight 10% → kontribusi = 5.0 points konstan

Ini berarti **10% dari scoring formula (di mode non-BPJS) saat ini dead weight** yang tidak pernah membedakan satu emiten dari lainnya.

## Dampak pada smart_money_score

Karena `broker_net_buy_{N}d` selalu None:
- Di `score_smart_money()`, loop `accumulation_lookbacks` yang menghitung `acc_count` dan `dist_count` dari `broker_net_buy_{N}d` **selalu menghasilkan 0** ketika `accumulation_window_count` tidak tersedia dari bandarmology stage.
- Untungnya, `accumulation_window_count` dan `distribution_window_count` SUDAH dihitung di `bandarmology.py` → jadi ketika data Stage 3B tersedia, `acc_count`/`dist_count` diisi dari field tersebut (bukan dari `broker_net_buy_{N}d`).

## Rekomendasi Perbaikan (per Prioritas)

1. **P1 (Task 8):** Implementasi `MarketRegimeFilter` → akan mengisi `market_regime_score` dari data IHSG riil.
2. **P1 (Task 7):** Tambahkan `top3_buyer_dominance` = `top3_buyer_value / top3_seller_value` di output `calculate_broker_features()`.  
3. **P2:** Pertimbangkan apakah `sector_strength_score` layak diimplementasi atau di-drop dari formula (set weight ke 0).
4. **P2:** Field `broker_net_buy_{N}d` bisa diisi dari `normalize_broker_summary_long` output dengan pivot per window — atau dihapus dari logic scoring karena sudah di-cover oleh `accumulation_window_count`.
