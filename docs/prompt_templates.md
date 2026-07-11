# Prompt Templates — IDX Interday Trading

Copy-paste salah satu prompt ini ke chat untuk memulai workflow trading.

---

## 1. Analisis Malam (Evening Scan)

```
Tolong lakukan analisis trading lengkap untuk besok.
Modal: Rp500.000
Universe: LQ45
Strategi: interday

Langkah:
1. Cek sentimen pasar terkini lewat web search
2. Cek smart money (bandar) dan insider activity
3. Cek dividen/ex-date besok
4. Jalankan pipeline screening
5. Kasih rekomendasi lengkap: saham apa, entry/TP/SL, berapa lot, kenapa
```

---

## 2. Analisis Cepat (Quick Check)

```
Cek saham [TICKER] sekarang — layak beli atau tidak?
Modal: Rp500.000

Saya butuh:
- Posisi teknikal (support/resistance, trend)
- Apakah bandar/insider sedang masuk
- Foreign flow terakhir
- Apakah ada ex-date mendekati
- VWAP dan gap terakhir (kalau tersedia)
- Kesimpulan: beli, tunggu, atau hindari
```

---

## 3. Modal Terbatas (Small Capital Optimization)

```
Saya punya modal Rp500.000. Tolong carikan saham yang:
- Harga per lembar < Rp500 (agar bisa beli minimal 1 lot)
- Ada sinyal akumulasi (bandar/insider)
- Risk/reward minimal 1:1
- Potensi profit minimal 5%

Jalankan pipeline, lalu kalau tidak ada yang lolos, simulasikan what-if dengan modal Rp1.000.000 untuk lihat apa yang bisa dibeli.
```

---

## 4. Monitoring Pagi (Morning Confirmation)

```
Kemarin malam saya sudah run pipeline (run ID: [RUN_ID]).
Sekarang pagi, market sudah buka.

Tolong:
1. Jalankan morning confirmation (orderbook check)
2. Cek VWAP dan opening gap untuk kandidat utama
3. Update rekomendasi berdasarkan kondisi live
4. Kasih keputusan final: eksekusi atau tunggu
```

---

## 5. Review Weekend (Saturday/Sunday)

```
Sekarang weekend. Tolong review:
1. Bagaimana hasil run terakhir minggu ini?
2. Apa yang bisa diperbaiki (diagnose + suggest)
3. Simulasikan what-if kalau modal dinaikkan
4. Saham mana yang worth dipantau Senin?
5. Ada insider activity menarik minggu ini?
```

---

## 6. Sentimen & Katalis

```
Tolong analisis sentimen pasar Indonesia terkini:
1. Search berita IHSG dan market outlook
2. Cek komoditas (emas, CPO, batubara) — impact ke sektor mana
3. Ada IPO/dividen/rights issue yang mempengaruhi?
4. Cross-reference dengan smart money flow
5. Sektor mana yang paling menarik saat ini?

Berdasarkan temuan, sarankan 3-5 saham yang paling cocok untuk modal Rp500k.
```

---

## 7. Evaluasi Performa (Backtest Review)

```
Tolong evaluasi performa pipeline terakhir:
1. Bandingkan 2-3 run terakhir (compare_runs)
2. Cek signal validation — apakah ada degradasi
3. Win rate dan profit factor terakhir
4. Apa yang perlu diubah di parameter?
```

---

## 8. Bandar & Smart Money Focus

```
Tolong carikan saham yang sedang diakumulasi smart money:
1. Scan bandar activity (asing + domestik, 7 hari)
2. Cek insider buying terbaru
3. Cross-reference: saham yang bandar DAN insider sama-sama masuk
4. Dari yang ketemu, jalankan pipeline untuk cek teknikal + risk
5. Mana yang paling layak untuk modal Rp500k?
```

---

## 9. Spesifik BPJS (Beli Pagi Jual Siang)

```
Tolong carikan peluang BPJS untuk hari ini:
- Strategi: beli di sesi pagi, jual di sesi siang
- Modal: Rp500.000
- Target: 1-2% intraday
- Syarat: spread ketat (1 tick), likuiditas tinggi, momentum positif

Cek:
1. Saham yang opening gap up (positif tapi tidak terlalu besar)
2. Volume pagi tinggi (VWAP confirmation)
3. Orderbook supportive (bid depth > offer)
4. Tidak ada ex-date hari ini
```

---

## 10. Custom Universe

```
Tolong analisis saham-saham berikut: [TICKER1, TICKER2, TICKER3, ...]
Modal: Rp[JUMLAH]
Strategi: [interday/bpjs]

Jalankan pipeline lengkap, lalu berikan:
- Ranking dari yang paling layak ke yang paling tidak
- Alasan per saham (kenapa layak/tidak)
- Entry, TP, SL untuk yang layak
- Risiko utama yang perlu diwaspadai
```

---

## Tips Penggunaan

- **Sebutkan modal** — pipeline butuh ini untuk sizing
- **Sebutkan timeframe** — interday (beberapa hari) atau BPJS (intraday)
- **Kalau weekend** — jangan minta run pipeline baru, minta review/what-if saja
- **Kalau 0 valid plans** — minta diagnose + suggest + what-if
- **Kalau mau cepat** — sebutkan ticker spesifik (bukan universe besar)
