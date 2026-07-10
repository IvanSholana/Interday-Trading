# Laporan Implementasi P2 - Strategy dan Scoring

Tanggal: 2026-07-10

## Perubahan

- Enam kontrak strategi eksplisit: breakout, pullback, rebound, momentum continuation, smart-money discovery, dan sideways compression.
- Setiap kontrak menyimpan eligibility gate, setup definition, entry trigger, invalidation, stop, target, time stop, allowed regime, required features, dan optional features.
- Kandidat tanpa trigger hanya dapat menjadi `WATCHLIST` atau `READY_SOON`; compression tidak dapat menjadi execution-ready sebelum breakout.
- Ranking BPJS dipisahkan menjadi `alpha_score`, `execution_quality_score`, `risk_feasibility_score`, dan `confidence_score`.
- Affordability/risk/net-profit feasibility tidak lagi dihitung sebagai directional alpha.
- Estimasi probability-to-TP hanya digunakan bila provider tervalidasi menyuplai nilainya; sistem tidak membuat probabilitas palsu.
- Broker dominance menggunakan bounded buyer/seller share, bukan rasio tak terbatas.
- Broker-flow score tidak lagi menerima bonus momentum, CLV, relative activity, atau technical context.
- Normalisasi broker flow mendukung average traded value, daily traded value, rolling z-score, dan free-float market cap bila tersedia.
- Audit korelasi Spearman tersedia dan hanya melaporkan pasangan berpotensi double-count; fungsi ini tidak mengubah bobot otomatis.

## Dampak keputusan

- Perubahan memengaruhi ranking dan batas status execution, bukan hard safety gates.
- Kandidat berkualitas tanpa trigger tetap ditemukan tetapi tidak dapat dieksekusi.
- Missing optional broker/orderbook/probability evidence tetap menurunkan confidence, bukan otomatis `REJECT`.
- Risk feasibility tetap menjadi gate terpisah meskipun tidak masuk alpha/ranking score.

## Test

- Full suite: `508 passed`, `1 warning`.
- Focused strategy/scoring/bandarmology: `56 passed` pada kelompok final yang relevan.
- Test mencakup seluruh strategy route, trigger/status cap, allowed regime, risk/alpha separation, optional TP probability, bounded dominance, low coverage, technical double-count prevention, normalization, dan correlation audit.

## Remaining research risks

- Bobot ranking belum dikalibrasi melalui walk-forward historical dataset yang lengkap.
- TP probability belum tersedia sampai ada outcome dataset point-in-time yang valid.
- Free-float dan historical broker-flow distribution belum memiliki coverage penuh.
- Korelasi feature dan ablation harus dijalankan per regime dan periode, bukan hanya pada satu sampel agregat.

## Acceptance

P2 implementation foundation selesai, tetapi status repository tetap `P0_COMPLETE_P1_NOT_COMPLETE` sampai historical point-in-time datasets dan robustness evidence tersedia.
