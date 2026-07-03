# Requirements Document

## Introduction

Dokumen ini mendefinisikan requirement untuk peningkatan menyeluruh ("super maksimal") pada pipeline screening interday IDX di `src/interday_liquidity_screener/`. Tujuan utamanya adalah **meningkatkan edge/probabilitas** hasil algoritma: memastikan bahwa sinyal yang dihasilkan (entry setup, bandarmology, trade plan) benar-benar punya bukti empiris keunggulan, bukan hanya threshold pilihan tangan.

Pipeline saat ini terdiri dari Stage 1 (screening likuiditas), Stage 2 (konteks teknikal), Stage 3A (koleksi broker summary Stockbit), Stage 3B (scoring bandarmology), dan Stage 4 (trade plan + risk management). Stage 5 (backtesting) belum ada. Tanpa backtesting, tidak ada satupun threshold yang bisa dibuktikan menambah edge.

Karena itu, peningkatan diorganisasi menjadi **kapabilitas berprioritas dan bisa dirilis independen**, dengan **framework backtesting sebagai fondasi (prioritas tertinggi)** karena ia yang memungkinkan pengukuran apakah perubahan lain benar-benar menambah edge.

Konteks pengguna: trader ritel personal, target pergerakan **2-5%** per trade (interday, bukan pembelian besar). Modal adalah parameter yang dapat dikonfigurasi. Biaya transaksi dan slippage harus dimodelkan agar hasil backtest realistis. Data broker summary historis Stockbit **dapat diambil** untuk rentang backtest.

### Prioritas Kapabilitas

- **P0 (Fondasi):** Requirement 1-3 — Framework Backtesting/Validasi Walk-Forward, Pemodelan Biaya & Slippage, Metrik Edge & Pelaporan Segmentasi.
- **P1 (Peningkatan Sinyal Berbasis Bukti):** Requirement 4-7 — Bandarmology scoring diperbaiki, Filter Regime/Breadth Pasar, Konfirmasi Multi-bar, Data Adjusted Close.
- **P2 (Realisme Eksekusi & Kebersihan Config):** Requirement 8-11 — Take-profit adaptif, Position sizing dibatasi likuiditas, Perataan waktu window broker, Pembersihan config mati (`min_volume_ratio`, `max_return_5d`).
- **P3 (Perlindungan Tambahan):** Requirement 12 — Blackout earnings/corporate action.

## Glossary

- **Pipeline**: Keseluruhan sistem screening interday di `src/interday_liquidity_screener/`.
- **Backtest_Engine**: Komponen baru (Stage 5) yang menjalankan simulasi historis walk-forward atas sinyal pipeline.
- **Walk_Forward**: Metode evaluasi di mana keputusan pada tanggal T hanya menggunakan data sampai tanggal T (tanpa melihat masa depan), lalu hasil diukur pada bar setelah T.
- **Trade_Simulation**: Satu entri hipotetis yang disimulasikan Backtest_Engine dari sinyal entry sampai exit (TP, SL, atau time-stop).
- **Entry_Signal**: Sinyal masuk yang dihasilkan pipeline (entry_setup / technical_context / trade_status VALID).
- **Exit_Event**: Peristiwa yang menutup Trade_Simulation: TP1-hit, TP2-hit, SL-hit, atau Time_Stop.
- **Time_Stop**: Batas maksimum jumlah hari perdagangan sebuah Trade_Simulation ditahan sebelum ditutup pada harga penutupan hari terakhir.
- **MFE**: Maximum Favorable Excursion — pergerakan menguntungkan terbesar (dalam %) selama trade hidup.
- **MAE**: Maximum Adverse Excursion — pergerakan merugikan terbesar (dalam %) selama trade hidup.
- **Expectancy**: Rata-rata hasil per trade = (win_rate × avg_win) − (loss_rate × avg_loss), dinyatakan dalam % return atau R-multiple.
- **R_Multiple**: Hasil trade dinyatakan sebagai kelipatan risiko awal (jarak entry ke stop-loss).
- **Cost_Model**: Model biaya transaksi (fee beli, fee jual) dan slippage yang diterapkan pada setiap Trade_Simulation.
- **Slippage**: Selisih antara harga sinyal dan harga eksekusi yang diasumsikan, dinyatakan dalam tick IDX atau persen.
- **Bandarmology_Score**: Skor 0-100 dari `bandarmology.py` yang mengukur akumulasi/distribusi bandar dari aliran broker.
- **HHI**: Herfindahl-Hirschman Index — ukuran konsentrasi; di sini `buyer_hhi`/`seller_hhi` mengukur seberapa terkonsentrasi nilai beli/jual pada sedikit broker.
- **Top3_Dominance**: Perbandingan `top3_buyer_value` vs `top3_seller_value` sebagai proksi dominasi arah bandar.
- **Close_Vs_Top_Buyer_Avg**: Selisih relatif harga penutupan terhadap harga rata-rata pembeli utama; nilai tinggi = risiko distribusi (harga sudah jauh di atas average bandar).
- **Market_Regime**: Kondisi global pasar (tren IHSG dan/atau breadth % saham di atas MA) yang menjadi gerbang izin trading.
- **Breadth**: Persentase saham dalam universe yang berada di atas moving average tertentu (mis. MA50).
- **Adjusted_Close**: Harga penutupan yang disesuaikan untuk split & dividen.
- **Raw_Close**: Harga penutupan mentah (belum disesuaikan), dipakai untuk validasi tick-size IDX.
- **Segment**: Pengelompokan hasil backtest berdasarkan dimensi seperti entry_setup, technical_context, atau bandarmology_signal.
- **Config**: Objek konfigurasi (`ScreenerConfig`, `TradePlanConfig`, dan config baru untuk Backtest_Engine).

## Requirements

### Requirement 1: Framework Backtesting Walk-Forward (Stage 5) — P0

**User Story:** Sebagai trader ritel, saya ingin mensimulasikan sinyal pipeline secara historis dengan metode walk-forward, sehingga saya punya bukti empiris apakah sinyal benar-benar punya edge sebelum saya pakai untuk trading nyata.

#### Acceptance Criteria

1. WHEN Backtest_Engine dijalankan atas satu universe ticker dan rentang tanggal historis, THE Backtest_Engine SHALL menghasilkan satu Trade_Simulation untuk setiap Entry_Signal yang muncul pada tanggal keputusan di dalam rentang tersebut.
2. WHEN Backtest_Engine membentuk Entry_Signal pada tanggal keputusan T, THE Backtest_Engine SHALL hanya menggunakan data harga dan indikator yang tersedia sampai dan termasuk tanggal T (tanpa data setelah T).
3. WHEN sebuah Trade_Simulation dibuka, THE Backtest_Engine SHALL menentukan Exit_Event sebagai peristiwa pertama yang terpenuhi di antara TP1-hit, SL-hit, atau Time_Stop, dengan urutan evaluasi harga intrabar yang deterministik dan terdokumentasi.
4. WHEN pada satu bar harga menyentuh baik level stop-loss maupun level take-profit, THE Backtest_Engine SHALL memilih stop-loss sebagai Exit_Event (asumsi konservatif).
5. WHEN sebuah Trade_Simulation mencapai batas Time_Stop tanpa menyentuh TP atau SL, THE Backtest_Engine SHALL menutup trade pada harga penutupan bar terakhir dan mencatatnya sebagai exit Time_Stop.
6. THE Backtest_Engine SHALL menghasilkan sebuah ledger trade yang memuat, untuk setiap Trade_Simulation: ticker, tanggal entry, harga entry, harga stop, harga TP1/TP2, tanggal exit, harga exit, jenis Exit_Event, return bersih, R_Multiple, MFE, MAE, dan holding_days.
7. IF data historis untuk sebuah ticker tidak cukup untuk menghitung indikator yang dibutuhkan pada tanggal keputusan, THEN THE Backtest_Engine SHALL melewati ticker tersebut pada tanggal itu dan mencatat alasan pelewatan.
8. WHERE pengguna menyediakan parameter time-stop bernilai positif, THE Backtest_Engine SHALL menggunakan nilai time-stop tersebut alih-alih nilai default.
9. IF pengguna menyediakan parameter time-stop bernilai nol atau negatif, THEN THE Backtest_Engine SHALL memperlakukannya sebagai masukan tidak valid dan memakai nilai time-stop default.

### Requirement 2: Pemodelan Biaya Transaksi & Slippage — P0

**User Story:** Sebagai trader ritel, saya ingin backtest memperhitungkan fee dan slippage, sehingga hasil edge yang dilaporkan mencerminkan keuntungan bersih yang realistis, bukan keuntungan kotor yang menyesatkan.

#### Acceptance Criteria

1. WHEN Backtest_Engine menghitung return bersih sebuah Trade_Simulation, THE Cost_Model SHALL menerapkan formula eksak return_bersih = return_kotor − fee_beli − fee_jual sesuai parameter yang dikonfigurasi.
2. WHEN Backtest_Engine menentukan harga eksekusi entry dan exit, THE Cost_Model SHALL menerapkan Slippage yang dikonfigurasi terhadap harga sinyal dengan arah yang merugikan trader (entry lebih mahal, exit lebih murah).
3. WHERE pengguna menyediakan parameter fee beli, fee jual, dan Slippage, THE Cost_Model SHALL menggunakan nilai tersebut alih-alih nilai default.
4. THE Cost_Model SHALL menerapkan harga eksekusi hasil Slippage yang tetap valid terhadap tick-size IDX.
5. THE ledger trade SHALL mencatat baik return kotor (sebelum biaya) maupun return bersih (setelah biaya dan slippage) untuk setiap Trade_Simulation.

### Requirement 3: Metrik Edge & Pelaporan Tersegmentasi — P0

**User Story:** Sebagai trader ritel, saya ingin ringkasan metrik edge yang dipecah per jenis sinyal, sehingga saya tahu segmen mana yang menguntungkan dan segmen mana yang harus dibuang.

#### Acceptance Criteria

1. WHEN backtest selesai, THE Backtest_Engine SHALL menghitung metrik agregat berikut dari ledger trade: jumlah trade, win_rate, avg_win, avg_loss, Expectancy, rasio TP-hit vs SL-hit, dan rata-rata holding_days.
2. WHEN backtest selesai, THE Backtest_Engine SHALL menghitung distribusi MFE dan MAE (minimal median dan persentil) dari seluruh Trade_Simulation.
3. WHEN backtest selesai, THE Backtest_Engine SHALL menghasilkan metrik edge yang dipecah per Segment untuk dimensi entry_setup, technical_context, dan bandarmology_signal.
4. WHERE tidak ada Trade_Simulation dalam sebuah Segment, THE Backtest_Engine SHALL memvalidasi dan menandai Segment tersebut sebagai tidak punya sampel sebelum melakukan perhitungan apa pun, sehingga tidak pernah terjadi pembagian dengan nol.
5. WHERE sebuah Segment memuat objek Trade_Simulation, THE Backtest_Engine SHALL memperlakukannya sebagai Segment yang punya sampel meskipun trade tersebut tidak menghasilkan posisi tereksekusi.
6. THE Backtest_Engine SHALL menyimpan hasil metrik dan ledger ke file output yang dapat ditinjau (mis. CSV) di direktori output.
7. WHEN sebuah metrik win_rate atau Expectancy dihitung dari jumlah sampel di bawah ambang minimum yang dikonfigurasi, THE Backtest_Engine SHALL menandai metrik tersebut sebagai tidak signifikan secara statistik.

### Requirement 4: Perbaikan Scoring Bandarmology — P1

**User Story:** Sebagai trader, saya ingin skor bandarmology memakai sinyal konsentrasi dan dominasi bandar yang sudah dihitung tetapi belum dipakai, sehingga skor lebih mencerminkan perilaku bandar nyata.

#### Acceptance Criteria

1. WHEN `calculate_bandarmology_score` menghitung skor sebuah ticker, THE Pipeline SHALL menyertakan kontribusi dari `buyer_hhi` sebagai ukuran konsentrasi pembeli.
2. WHEN `calculate_bandarmology_score` menghitung skor sebuah ticker, THE Pipeline SHALL menyertakan kontribusi dari Top3_Dominance (`top3_buyer_value` relatif terhadap `top3_seller_value`).
3. WHEN `calculate_bandarmology_score` menghitung skor sebuah ticker, THE Pipeline SHALL menyertakan kontribusi dari Close_Vs_Top_Buyer_Avg sebagai ukuran risiko distribusi.
4. WHEN Close_Vs_Top_Buyer_Avg melebihi ambang risiko distribusi yang dikonfigurasi, THE Pipeline SHALL menurunkan Bandarmology_Score ticker tersebut.
5. THE Bandarmology_Score SHALL tetap berada dalam rentang 0 sampai 100 setelah seluruh kontribusi diterapkan.
6. WHEN kontribusi `buyer_hhi`, Top3_Dominance, atau Close_Vs_Top_Buyer_Avg bernilai nol atau negatif, THE Pipeline SHALL tetap menyertakan kontribusi tersebut ke dalam perhitungan Bandarmology_Score.
7. IF sebuah sinyal masukan (`buyer_hhi`, Top3_Dominance, atau Close_Vs_Top_Buyer_Avg) tidak tersedia untuk sebuah ticker, THEN THE Pipeline SHALL menghitung skor dari sinyal yang tersedia tanpa menghasilkan error.
8. THE Pipeline SHALL mencatat komponen kontributor Bandarmology_Score sehingga skor dapat ditelusuri per faktor.

### Requirement 5: Filter Regime / Breadth Pasar — P1

**User Story:** Sebagai trader, saya ingin pipeline mempertimbangkan kondisi pasar global (IHSG / breadth), sehingga sinyal beli tidak dikeluarkan saat pasar sedang risk-off.

#### Acceptance Criteria

1. WHEN pipeline mengevaluasi kandidat trade, THE Pipeline SHALL menghitung Market_Regime dari tren indeks IHSG dan/atau Breadth universe pada tanggal keputusan.
2. WHILE Market_Regime tidak berada dalam kondisi risk-on yang terdefinisi secara pasti (termasuk kondisi risk-off, ambigu, atau gagal dihitung), THE Pipeline SHALL menandai kandidat trade dengan status penurunan izin (gate) alih-alih meloloskannya sebagai valid.
3. WHERE pengguna mengaktifkan opsi untuk mengabaikan gerbang Market_Regime, THE Pipeline SHALL memproses kandidat tanpa menerapkan filter regime.
4. THE Pipeline SHALL menghitung Market_Regime hanya dari data sampai tanggal keputusan agar konsisten dengan evaluasi Walk_Forward.
5. THE Pipeline SHALL mencatat nilai Market_Regime yang dipakai pada output sehingga keputusan gate dapat ditelusuri.

### Requirement 6: Konfirmasi Multi-bar untuk Breakout/Rebound — P1

**User Story:** Sebagai trader, saya ingin klasifikasi breakout dan rebound dikonfirmasi oleh lebih dari satu bar, sehingga sinyal palsu dari satu snapshot berkurang.

#### Acceptance Criteria

1. WHEN pipeline mengklasifikasikan setup BREAKOUT, THE Pipeline SHALL mensyaratkan konfirmasi lintas beberapa bar terakhir sesuai jumlah bar yang dikonfigurasi sebelum menandai setup sebagai terkonfirmasi.
2. WHEN pipeline mengklasifikasikan setup REBOUND, THE Pipeline SHALL mensyaratkan konfirmasi lintas beberapa bar terakhir sesuai jumlah bar yang dikonfigurasi sebelum menandai setup sebagai terkonfirmasi.
3. IF konfirmasi multi-bar belum terpenuhi untuk sebuah setup, THEN THE Pipeline SHALL menempatkan kandidat pada status menunggu konfirmasi alih-alih valid.
4. WHEN kriteria konfirmasi multi-bar terpenuhi untuk kandidat yang sedang menunggu, THE Pipeline SHALL memindahkan kandidat tersebut ke status terkonfirmasi.
5. WHERE pengguna mengatur jumlah bar konfirmasi secara eksplisit, THE Pipeline SHALL menggunakan jumlah bar tersebut; jika tidak ada konfigurasi eksplisit, THE Pipeline SHALL memakai jumlah bar default.
6. THE Pipeline SHALL tetap dapat menghasilkan keputusan pada satu tanggal keputusan dengan hanya menggunakan bar sampai tanggal tersebut (kompatibel dengan Walk_Forward).

### Requirement 7: Penggunaan Adjusted Close untuk Indikator — P1

**User Story:** Sebagai trader, saya ingin indikator dihitung dari harga yang disesuaikan split/dividen, sehingga MA200 dan return jangka panjang tidak terdistorsi oleh corporate action.

#### Acceptance Criteria

1. WHEN pipeline menghitung moving average, RSI, ATR, dan return, THE Pipeline SHALL menggunakan Adjusted_Close sebagai basis harga.
2. WHEN pipeline memvalidasi harga terhadap tick-size IDX pada trade plan, THE Pipeline SHALL menggunakan Raw_Close alih-alih Adjusted_Close.
3. IF Adjusted_Close tidak tersedia untuk sebuah ticker, THEN THE Pipeline SHALL menggunakan Raw_Close sebagai cadangan dan menandai status penyesuaian (tidak diterapkan) di dalam data output sehingga sistem lain dapat melihatnya.
4. THE Pipeline SHALL menghasilkan indikator yang identik dengan versi lama untuk ticker tanpa split/dividen dalam periode data (tidak ada regresi pada kasus tanpa corporate action).

### Requirement 8: Take-Profit Adaptif — P2

**User Story:** Sebagai trader dengan target 2-5%, saya ingin take-profit disesuaikan dengan volatilitas atau struktur harga, sehingga target tidak selalu dipatok kaku 5%/8% terlepas dari karakter saham.

#### Acceptance Criteria

1. WHEN pipeline menghitung level take-profit, THE Pipeline SHALL menurunkan TP1 dan TP2 dari ukuran adaptif berbasis ATR dan/atau level resistensi struktur harga, dengan menjaga jarak minimum TP1 lebih dari entry + 0.5×ATR dan TP2 lebih dari entry + 1.0×ATR.
2. WHERE pengguna memilih mode take-profit tetap, THE Pipeline SHALL memakai persentase tetap yang dikonfigurasi alih-alih take-profit adaptif.
3. THE Pipeline SHALL memastikan TP1 lebih kecil dari TP2 dan keduanya berada di atas harga entry untuk trade long.
4. THE level take-profit hasil perhitungan SHALL dibulatkan ke tick-size IDX yang valid sebelum digunakan pada trade plan final.
5. WHEN take-profit adaptif menghasilkan target di luar rentang yang wajar yang dikonfigurasi (mis. terlalu dekat atau terlalu jauh), THE Pipeline SHALL membatasinya (clamp) ke batas rentang tersebut.

### Requirement 9: Position Sizing Dibatasi Likuiditas — P2

**User Story:** Sebagai trader, saya ingin ukuran posisi dibatasi oleh likuiditas saham, sehingga rencana tidak mengasumsikan pengisian order yang tidak realistis pada saham tipis.

#### Acceptance Criteria

1. WHEN pipeline menghitung ukuran posisi, THE Pipeline SHALL membatasi nilai posisi maksimum sebesar persentase yang dikonfigurasi dari `avg_value_20d` ticker.
2. WHEN batas likuiditas lebih kecil dari batas risiko dan batas modal, THE Pipeline SHALL memakai batas terkecil di antara ketiga batas tersebut sebagai ukuran posisi final.
3. WHERE pengguna menyediakan persentase batas likuiditas, THE Pipeline SHALL menggunakan persentase tersebut alih-alih nilai default.
4. THE Pipeline SHALL mencatat batas mana (risiko, modal, atau likuiditas) yang menjadi pengikat ukuran posisi final.

### Requirement 10: Perataan Waktu Window Broker Flow — P2

**User Story:** Sebagai trader, saya ingin window pengambilan broker flow berakhir pada tanggal terakhir data Stage 2, sehingga sinyal bandarmology sejalan waktu dengan konteks teknikal.

#### Acceptance Criteria

1. WHEN Stage 3A menentukan rentang tanggal koleksi broker summary, THE Pipeline SHALL menetapkan tanggal akhir window sama dengan `last_date` dari Stage 2 untuk ticker terkait.
2. IF `last_date` Stage 2 tidak tersedia untuk sebuah ticker, THEN THE Pipeline SHALL memakai tanggal akhir default yang dikonfigurasi, mencatat ketidaksesuaian, dan tetap melanjutkan proses meskipun pencatatan gagal.
3. THE Pipeline SHALL mencatat tanggal awal dan akhir window broker flow yang dipakai pada output Stage 3A.

### Requirement 11: Pembersihan Config Mati — P2

**User Story:** Sebagai pemelihara kode, saya ingin parameter config yang tidak terpakai (`min_volume_ratio`, `max_return_5d`) diberlakukan atau dihapus, sehingga tidak ada parameter menyesatkan yang tampak berpengaruh padahal tidak.

#### Acceptance Criteria

1. THE Pipeline SHALL menerapkan parameter `min_volume_ratio` sebagai filter pada logika screening likuiditas Stage 1.
2. WHERE parameter `max_return_5d` dipertahankan, THE Pipeline SHALL menerapkannya pada logika screening likuiditas Stage 1.
3. IF sebuah parameter tidak diterapkan secara aktif pada logika apa pun, THEN THE Pipeline SHALL menghapusnya dari Config dan antarmuka CLI agar tidak lagi terekspos.
4. THE Config SHALL tidak memuat parameter yang terekspos ke CLI namun tidak berpengaruh pada perilaku apa pun.

### Requirement 12: Blackout Earnings / Corporate Action — P3

**User Story:** Sebagai trader, saya ingin sistem menghindari entry di sekitar tanggal earnings atau corporate action, sehingga saya tidak terkena lompatan harga tak terduga.

#### Acceptance Criteria

1. WHERE data tanggal earnings atau corporate action tersedia untuk sebuah ticker, THE Pipeline SHALL menandai kandidat yang tanggal keputusannya berada di dalam jendela blackout yang dikonfigurasi dengan status blackout.
2. WHEN sebuah kandidat berada dalam jendela blackout, THE Pipeline SHALL mencegahnya menjadi trade plan valid selama opsi blackout aktif.
3. WHERE pengguna menonaktifkan blackout, THE Pipeline SHALL memproses kandidat tanpa memeriksa jendela blackout.
4. THE Pipeline SHALL mencatat baik kasus keberhasilan pengambilan data earnings/corporate action maupun kasus ketiadaan data.
5. IF data earnings/corporate action tidak tersedia untuk sebuah ticker, THEN THE Pipeline SHALL memproses ticker tanpa blackout dan tetap melanjutkan meskipun pencatatan gagal.
