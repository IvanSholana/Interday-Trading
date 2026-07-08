# Guidebook Dashboard Interday Trading

Panduan ini dibuat untuk memakai website lokal dengan lebih santai, rapi, dan tidak tersesat di istilah teknis. Anggap dashboard ini seperti meja kerja harian: masukkan daftar saham, jalankan analisis, baca hasilnya, lalu pilih mana yang layak dipantau lebih serius.

> Catatan penting: tool ini adalah alat bantu riset, bukan rekomendasi investasi dan bukan tombol auto order.

## 1. Gambaran Besar

Dashboard menjalankan pipeline dari awal sampai akhir:

1. Cek saham yang cukup ramai transaksinya.
2. Cek kondisi teknikal.
3. Ambil dan nilai broker-flow dari Stockbit.
4. Cek orderbook.
5. Buat rencana trade dan simulasi/backtest.
6. Buat laporan ringkas dari hasil pipeline.

Bahasa sederhananya:

- **Stage** = langkah kerja.
- **Pipeline** = semua stage yang dijalankan berurutan.
- **Cache harga lokal** = database kecil di komputer agar data harga tidak diambil ulang terus dari API.
- **Run** = satu sesi analisis. Setiap run disimpan di folder baru.

## 2. Cara Menjalankan Website

Buka terminal PowerShell di folder project, lalu jalankan:

```powershell
python -m src.interday_liquidity_screener.server
```

Kalau package sudah ter-install dan script tersedia:

```powershell
interday-web
```

Setelah itu buka browser Anda di alamat:

```text
http://localhost:8000/
```

## 3. Alur Harian Yang Disarankan

Untuk pemakaian normal, ikuti urutan ini:

1. Buka dashboard.
2. Isi atau cek token API di sidebar.
3. Pilih tanggal analisis.
4. Pilih strategi: `interday` atau `bpjs`.
5. Masukkan daftar saham.
6. Jalankan Stage 1 sampai Stage 6.
7. Baca tab Overview.
8. Buka Results Explorer untuk filter saham.
9. Buka Reports untuk membaca ringkasan Stage 6.
10. Simpan catatan pribadi sebelum mengambil keputusan.

Kalau baru mencoba, gunakan daftar kecil dulu, misalnya 10 sampai 30 saham. Setelah yakin alurnya benar, baru pakai daftar besar.

## 4. Sidebar: Pengaturan Utama

Sidebar adalah panel kendali utama.

### Folder Hasil Run

Default:

```text
data/output/ui_runs
```

Biarkan default kalau tidak punya alasan khusus. Setiap kali run, dashboard membuat folder baru seperti:

```text
data/output/ui_runs/20260705_091530
```

Artinya hasil lama tidak tertimpa.

### Database Harga Lokal

Default:

```text
data/cache/market_data.sqlite
```

Ini database cache harga. Fungsinya agar data harga yang sudah pernah diambil tidak diambil ulang setiap hari.

Gunakan toggle **Ambil ulang harga dari API** hanya kalau:

- data terasa aneh,
- ingin memaksa update,
- cache rusak,
- atau baru mengganti sumber data.

Kalau tidak, biarkan mati agar lebih hemat request API.

### Tanggal Analisis

Pilih tanggal bursa yang ingin dianalisis. Biasanya pakai tanggal perdagangan terakhir.

Jika hari ini libur bursa, gunakan tanggal bursa terakhir, bukan tanggal kalender hari ini.

### Strategi

Ada dua mode:

- **interday**: rencana trade beberapa hari. Lebih cocok untuk swing pendek.
- **bpjs**: mode lebih cepat/intraday. Filter lebih ketat dan orderbook lebih penting.

Untuk mayoritas screening santai, mulai dari `interday`.

### Laporan AI Simulasi

Jika aktif, Stage 6 membuat laporan tanpa memanggil API DeepSeek.

Gunakan aktif saat:

- sedang testing,
- belum punya API key,
- ingin menghemat biaya,
- atau hanya ingin cek alur pipeline.

Matikan hanya kalau benar-benar ingin laporan AI dari API DeepSeek.

## 5. Token/API Key Sementara

Di sidebar ada bagian **Token/API key sementara**.

Gunanya untuk memasukkan token langsung dari website tanpa edit file `.env`.

### Stockbit Token

Dipakai untuk:

- Stage 3A broker-flow.
- Stage 3C orderbook.

Kalau token Stockbit sering berubah, tempel token baru di sini. Jika token ditempel dengan awalan `Bearer`, dashboard akan membersihkan otomatis.

Contoh yang boleh ditempel:

```text
Bearer eyJhbGciOi...
```

Atau:

```text
eyJhbGciOi...
```

Keduanya akan dipakai dengan benar.

### DeepSeek API Key

Dipakai hanya jika:

- Stage 6 dijalankan,
- dan **Laporan AI simulasi** dimatikan.

Kalau masih dry-run, DeepSeek API key tidak wajib.

### Apakah Token Disimpan?

Tidak. Input ini hanya berlaku untuk sesi dashboard yang sedang berjalan.

Kalau dashboard ditutup dan dibuka ulang, isi token lagi atau pakai `.env`.

## 6. Run Pipeline: Tempat Mulai Analisis

Tab **Run Pipeline** adalah layar utama untuk menjalankan analisis.

### File Daftar Saham

Default:

```text
examples/tickers.txt
```

Isi file bisa:

```text
BBCA
BMRI
TLKM
```

Atau:

```text
BBCA.JK
BMRI.JK
TLKM.JK
```

Dashboard akan menormalkan ticker otomatis menjadi format `.JK`.

### Mode Daftar Saham

Di bagian **Mode daftar saham**, kamu bisa memilih sumber ticker:

- **Manual / upload sendiri**: pakai file, upload, atau editor seperti biasa.
- **Semua saham IDX**: membaca `data/input/universes/all_idx.txt`.
- **Saham syariah**: membaca `data/input/universes/syariah.txt`.
- **LQ45, IDX30, IDX80, JII, Kompas100, SRI-KEHATI, Bisnis-27, PEFINDO25**: membaca file preset masing-masing di `data/input/universes`.

File preset adalah file lokal. Artinya, kalau BEI mengubah konstituen indeks, cukup update isi file `.txt` tersebut. Baris komentar dengan awalan `#` aman dipakai untuk catatan sumber atau tanggal update.

### Upload TXT/CSV

Gunakan ini kalau punya file sendiri.

TXT sederhana:

```text
BBCA
BMRI
BRIS
```

CSV sederhana:

```csv
ticker
BBCA
BMRI
BRIS
```

### Editor Daftar Saham

Ini tempat paling enak untuk edit cepat.

Satu baris = satu saham.

Contoh:

```text
BBCA
BMRI
BRIS
TLKM
```

Kalau jumlah saham terbaca terlihat masuk akal, lanjut.

## 7. Memilih Stage

Default-nya semua stage dipilih. Itu pilihan terbaik untuk run lengkap.

### Stage 1 - Liquidity

Pertanyaan yang dijawab:

> Saham ini cukup ramai atau tidak?

Output penting:

- `HIGH_LIQUIDITY`
- `GOOD_LIQUIDITY`
- `MEDIUM_LIQUIDITY`
- `LOW_LIQUIDITY`
- `ILLIQUID`

Untuk trading, biasanya fokus ke `HIGH_LIQUIDITY` dan `GOOD_LIQUIDITY`.

### Stage 2 - Technical

Pertanyaan yang dijawab:

> Chart-nya sedang menarik, biasa saja, atau berbahaya?

Stage ini melihat trend, momentum, volatilitas, dan konteks entry.

Kolom penting:

- `technical_context`
- `entry_setup`
- `bandar_watch_eligible`

Kalau `bandar_watch_eligible = True`, saham bisa lanjut dicek broker-flow.

### Stage 3A - Stockbit Broker

Pertanyaan yang dijawab:

> Ambil data broker-flow dari Stockbit untuk saham yang layak dipantau.

Stage ini butuh Stockbit token.

Kalau hasilnya kosong, belum tentu bug. Bisa jadi:

- tidak ada saham yang lolos watchlist,
- token bermasalah,
- Stockbit membatasi request,
- atau API sedang tidak memberi data.

Jika kosong, Stage 3B akan memberi status `NO_BROKER_DATA`.

### Stage 3B - Bandarmology

Pertanyaan yang dijawab:

> Broker-flow cenderung akumulasi, netral, atau distribusi?

Status umum:

- `STRONG_ACCUMULATION`: broker-flow kuat mendukung.
- `MILD_ACCUMULATION`: cukup mendukung.
- `NEUTRAL_FLOW`: belum jelas.
- `MILD_DISTRIBUTION`: ada tekanan jual.
- `STRONG_DISTRIBUTION`: tekanan jual kuat.
- `NO_BROKER_DATA`: data broker tidak tersedia.

Untuk kandidat serius, biasanya cari akumulasi, bukan distribusi.

### Stage 3C - Orderbook

Pertanyaan yang dijawab:

> Kalau mau eksekusi, bid/offer-nya sehat atau rawan?

Stage ini melihat spread, antrean bid/offer, notasi, dan risiko eksekusi.

Stage ini juga butuh Stockbit token.

### Stage 4 - Trade Plan

Pertanyaan yang dijawab:

> Kalau saham ini layak, entry, stop loss, take profit, dan ukuran posisinya berapa?

Kolom penting:

- `trade_status`
- `entry_price`
- `stop_loss`
- `take_profit_1`
- `take_profit_2`
- `position_size_lots`
- `risk_reward_tp1`
- `risk_reward_tp2`

Fokus utama:

```text
trade_status = VALID_TRADE_PLAN
```

Selain itu biasanya berarti tunggu, skip, atau reject.

### Stage 5 - Backtest/Paper Journal

Pertanyaan yang dijawab:

> Kalau aturan ini diuji ke data historis, kira-kira hasilnya seperti apa?

Ingat: backtest bukan ramalan. Gunakan untuk mengecek apakah aturan masuk akal, bukan untuk merasa pasti menang.

### Stage 6 - Report

Pertanyaan yang dijawab:

> Dari semua hasil tadi, apa ringkasan dan ranking kandidatnya?

Jika dry-run aktif, laporan dibuat simulasi tanpa API AI.

Jika dry-run mati, butuh DeepSeek API key.

## 8. Pengaturan Periode

### Periode Cek Likuiditas

Default:

```text
3mo
```

Artinya Stage 1 melihat data sekitar 3 bulan.

Ini cukup untuk cek apakah saham aktif belakangan ini.

### Periode Teknikal/Backtest

Default:

```text
1y
```

Artinya Stage 2 dan backtest punya konteks data sekitar 1 tahun.

### Jendela Broker-Flow

Default:

```text
1D,3D,5D,10D,20D
```

Artinya dashboard melihat broker-flow dari beberapa jarak waktu.

Bahasa mudahnya:

- `1D`: sangat pendek.
- `3D`: beberapa hari terakhir.
- `5D`: sekitar seminggu bursa.
- `10D`: sekitar dua minggu bursa.
- `20D`: sekitar satu bulan bursa.

Jangan hanya percaya satu window. Sinyal lebih nyaman kalau beberapa window searah.

## 9. Tombol Jalankan Analisis

Tombol **Jalankan analisis** akan aktif jika:

- ticker terbaca,
- stage dipilih,
- token yang dibutuhkan tersedia,
- dan input tidak error.

Setelah diklik, dashboard membuat folder run baru dan menjalankan stage satu per satu.

Kalau ada stage gagal, pipeline berhenti di stage itu agar error tidak merembet ke hasil berikutnya.

## 10. Tab Overview

Tab ini untuk melihat ringkasan run.

Yang biasanya dicek:

- berapa saham masuk Stage 1,
- berapa yang likuid,
- berapa yang layak watchlist,
- berapa trade plan valid,
- apakah report tersedia,
- apakah file output lengkap.

Gunakan tab ini sebagai pemeriksaan cepat.

Kalau jumlah `valid plans` nol, bukan berarti dashboard rusak. Bisa jadi market memang tidak memberi setup yang layak menurut aturan.

## 11. Tab Results Explorer

Ini tab untuk bekerja paling banyak setelah run selesai.

Kamu bisa:

- memilih tabel hasil,
- mencari ticker,
- filter status,
- download CSV hasil filter.

Cara pakai yang enak:

1. Pilih **Stage 4 Trade Plan**.
2. Filter `trade_status`.
3. Cari `VALID_TRADE_PLAN`.
4. Cek risk/reward dan ukuran posisi.
5. Buka Stage 3B untuk melihat broker-flow.
6. Buka Stage 3C untuk melihat orderbook.

Jangan hanya melihat satu kolom. Kandidat bagus biasanya punya kombinasi:

- likuiditas cukup,
- teknikal mendukung,
- broker-flow tidak distribusi,
- orderbook tidak buruk,
- risk/reward masuk akal.

## 12. Tab Reports

Tab ini membaca hasil Stage 6.

Isi utamanya:

- laporan Markdown,
- ranking kandidat,
- catatan watchlist.

Gunakan report sebagai ringkasan, bukan pengganti membaca tabel.

Jika report belum ada, jalankan Stage 6 atau pastikan file Stage 6 tersedia.

## 13. Tab Cache & Settings

Gunanya untuk cek:

- lokasi database harga lokal,
- apakah token API terbaca,
- file apa saja yang ada di run terpilih.

Kalau harga tidak update, cek bagian database harga lokal dan toggle **Ambil ulang harga dari API**.

Kalau Stage 3A/3C tidak bisa jalan, cek status Stockbit token.

Kalau Stage 6 non-simulasi tidak bisa jalan, cek status DeepSeek API key.

## 14. Cara Membaca Status Penting

### Liquidity Bucket

- `HIGH_LIQUIDITY`: ramai dan nyaman untuk lanjut.
- `GOOD_LIQUIDITY`: cukup bagus.
- `MEDIUM_LIQUIDITY`: hati-hati, belum ideal.
- `LOW_LIQUIDITY`: kurang ramai.
- `ILLIQUID`: sebaiknya dihindari untuk workflow ini.

### Trade Candidate Bucket

- `STRONG_WATCH`: layak dipantau.
- `WATCH`: masih menarik, tapi belum kuat.
- `AVOID_FOR_NOW`: jangan dipaksakan.
- `INVALID_DATA`: data tidak cukup atau bermasalah.

### Bandarmology Signal

- `STRONG_ACCUMULATION`: broker-flow kuat mendukung.
- `MILD_ACCUMULATION`: broker-flow cukup mendukung.
- `NEUTRAL_FLOW`: belum ada arah jelas.
- `MILD_DISTRIBUTION`: waspada tekanan jual.
- `STRONG_DISTRIBUTION`: hindari untuk entry agresif.
- `NO_BROKER_DATA`: tidak ada data broker yang bisa dinilai.

### Trade Status

- `VALID_TRADE_PLAN`: rencana trade valid menurut aturan.
- `WAIT_*`: tunggu kondisi membaik.
- `REJECT_*`: ditolak oleh filter tertentu.
- `SKIPPED_*`: dilewati karena belum memenuhi syarat awal.
- `INVALID_DATA`: data tidak layak dipakai.

## 15. Output Disimpan Di Mana?

Setiap run disimpan di:

```text
data/output/ui_runs/NAMA_RUN
```

Contoh:

```text
data/output/ui_runs/20260705_091530
```

File yang umum:

- `stage1_liquidity.csv`
- `stage2_technical_context.csv`
- `stockbit/stage3a_bandar_detector_summary.csv`
- `stockbit/stage3a_broker_summary_long.csv`
- `stage3b_bandarmology_score.csv`
- `stage3c_orderbook_filter.csv`
- `stage4_trade_plan.csv`
- `stage5_interday_trades.csv`
- `stage5_interday_metrics.json`
- `stage6_llm_daily_report.md`

Kalau ingin membandingkan run hari ini dan kemarin, buka folder run yang berbeda dari dropdown **Baca hasil run**.

## 16. Resep Pemakaian Praktis

### Resep Aman Untuk Pemula

1. Strategi: `interday`.
2. Laporan AI simulasi: aktif.
3. Ambil ulang harga dari API: mati.
4. Stage: jalankan semua.
5. Daftar saham: mulai dari 20-50 ticker.
6. Fokus hasil: Stage 4 `VALID_TRADE_PLAN`.
7. Baca Stage 3B dan Stage 3C sebelum percaya kandidat.

### Resep Saat Token Stockbit Baru Diganti

1. Buka sidebar.
2. Buka **Token/API key sementara**.
3. Tempel token Stockbit baru.
4. Pastikan status menjadi **Stockbit siap dipakai**.
5. Jalankan Stage 3A/3C lagi.

### Resep Hemat API

1. Jangan aktifkan **Ambil ulang harga dari API** kecuali perlu.
2. Gunakan cache default.
3. Jalankan ticker secukupnya.
4. Naikkan jeda API Stockbit jika sering rate limit.

### Resep Cek Hasil Cepat

1. Buka Results Explorer.
2. Pilih Stage 4 Trade Plan.
3. Cari `VALID_TRADE_PLAN`.
4. Download filtered CSV jika perlu.
5. Baca Reports untuk ringkasan.

## 17. Error Umum Dan Artinya

### Token Stockbit Belum Ada

Artinya Stage 3A/3C tidak bisa mengambil data Stockbit.

Solusi:

- isi Stockbit token di sidebar,
- atau isi `STOCKBIT_TOKEN` di `.env`.

### Stockbit Token Expired/Invalid

Artinya token sudah kadaluarsa atau salah.

Solusi:

- login ulang ke Stockbit,
- ambil token baru,
- tempel ke sidebar.

### NO_BROKER_DATA

Artinya dashboard tidak punya data broker-flow yang bisa dinilai.

Ini bukan selalu error. Bisa terjadi karena:

- tidak ada data dari Stockbit,
- semua request gagal,
- ticker tidak masuk watchlist,
- token atau rate limit bermasalah.

Kalau banyak `NO_BROKER_DATA`, cek token dan log Stage 3A.

### Tidak Ada Valid Trade Plan

Artinya tidak ada saham yang lolos semua aturan.

Ini bisa normal, terutama saat market tidak mendukung.

Jangan memaksa entry hanya karena ingin ada trade.

### File Change / Rerun Di Streamlit

Streamlit mendeteksi file kode berubah.

Klik **Rerun** agar UI memakai versi terbaru.

## 18. Checklist Sebelum Percaya Satu Kandidat

Sebelum menganggap satu saham layak, cek:

- Apakah likuiditasnya `HIGH_LIQUIDITY` atau `GOOD_LIQUIDITY`?
- Apakah `technical_context` masuk akal?
- Apakah broker-flow bukan distribusi kuat?
- Apakah orderbook tidak terlalu buruk?
- Apakah `trade_status = VALID_TRADE_PLAN`?
- Apakah stop loss masuk akal?
- Apakah risk/reward cukup?
- Apakah ukuran posisi tidak terlalu besar?
- Apakah ada berita besar, suspensi, UMA, atau corporate action?

Kalau ragu, lebih baik masuk watchlist daripada memaksa trade.

## 19. Kebiasaan Baik

- Simpan catatan pribadi setelah membaca hasil.
- Jangan mengubah semua setting sekaligus; ubah satu-satu agar tahu dampaknya.
- Gunakan daftar saham yang bersih dan relevan.
- Jangan terlalu sering refresh API kalau tidak perlu.
- Jangan bagikan token/API key.
- Jangan commit file `.env`.
- Jangan jadikan output AI sebagai keputusan tunggal.

## 20. Ringkasan Super Singkat

Kalau ingin versi satu menit:

1. Isi token Stockbit di sidebar kalau mau Stage 3A/3C.
2. Pakai `interday` untuk mulai.
3. Biarkan cache aktif, jangan refresh API kecuali perlu.
4. Masukkan ticker satu baris per saham.
5. Klik **Jalankan analisis**.
6. Buka **Overview** untuk cek run berhasil.
7. Buka **Results Explorer** dan cari `VALID_TRADE_PLAN`.
8. Buka **Reports** untuk ringkasan.
9. Tetap cek manual sebelum mengambil keputusan.
