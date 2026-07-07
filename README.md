# WGOEN Instagram + Twitter/X Colab Scraper

Developed by WGOEN Developer.

Paket ini berisi notebook Google Colab dan script Python untuk membuat dataset sederhana dari Instagram dan Twitter/X.

Posisi teknis yang aman:

- Instagram memakai Python + `Instaloader`.
- Twitter/X memakai jalur stabil `manual/browser-assisted normalization`.
- `snscrape` disediakan hanya sebagai mode eksperimen, bukan jalur utama.

## Isi Paket

- `Instagram_Twitter_Scraper_Colab.ipynb` - notebook utama untuk Google Colab.
- `instagram_scraper.py` - script Instagram berbasis Instaloader.
- `twitter_scraper.py` - script normalisasi Twitter/X, plus mode eksperimen.
- `requirements.txt` - dependency utama yang stabil.
- `requirements-experimental.txt` - dependency tambahan untuk mode eksperimen Twitter/X.
- `samples/` - contoh output CSV dan JSON sintetis/sanitized.
- `NOTICE.md` - catatan hak pakai dan batasan publikasi.
- `LICENSE` - lisensi terbatas WGOEN, bukan lisensi open source bebas.

## Cara Pakai Cepat

1. Buka `Instagram_Twitter_Scraper_Colab.ipynb` di Google Colab.
2. Isi parameter target akun, tanggal, keyword, dan lokasi output.
3. Untuk Instagram, jalankan bagian Instaloader.
4. Untuk Twitter/X, gunakan input manual/browser-assisted lalu normalisasi ke CSV/JSON.
5. Pakai `snscrape_experimental` hanya kalau benar-benar mau mencoba mode eksperimen.

## Install Lokal

```bash
pip install -r requirements.txt
```

Jika ingin mencoba mode eksperimen Twitter/X:

```bash
pip install -r requirements-experimental.txt
```

## Contoh Instagram

```bash
python instagram_scraper.py \
  --username nama_akun_publik \
  --start-date 2026-06-01 \
  --end-date 2026-06-30 \
  --output-dir output/instagram
```

Jika akses publik dibatasi, jalankan dengan session Instaloader milik pengguna sendiri. Jangan bagikan file session ke repo publik.

## Contoh Twitter/X Stabil

Siapkan file hasil input manual atau browser-assisted, lalu normalisasi:

```bash
python twitter_scraper.py \
  --start-date 2026-06-01 \
  --end-date 2026-06-30 \
  --mode manual_csv \
  --input-file samples/sample_twitter_output.csv \
  --output-dir output/twitter
```

## Catatan Penting

Twitter/X sering mengubah proteksi dan endpoint public search. Karena itu, paket ini tidak menjanjikan scraping Twitter/X otomatis selalu berhasil. Jalur yang lebih stabil adalah mengumpulkan input secara manual/browser-assisted, lalu memakai script ini untuk membersihkan dan menyamakan format dataset.

Tidak ada cookie, password, token, session login, atau data pribadi pemilik WGOEN di paket ini.

## Hak Pakai

Copyright (c) 2026 WGOEN.

Trademark: Developed by WGOEN Developer.

Kode, notebook, dokumentasi, dan sample dalam paket ini dipublikasikan untuk preview dan pembelajaran terbatas. Penggunaan komersial, publikasi ulang, distribusi ulang, modifikasi untuk dijual kembali, atau klaim kepemilikan wajib mendapat izin tertulis dari WGOEN. Untuk izin penggunaan, hubungi `creative@wgoen.com`.
