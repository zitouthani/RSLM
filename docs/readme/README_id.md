# RSLM

RSLM adalah asisten dokumen lokal sumber terbuka yang menggunakan retrieval-augmented generation (RAG). Proyek ini menggabungkan Streamlit, FastAPI, Qdrant, Sentence Transformers, dan Ollama.

**Bahasa lain:** [Indeks bahasa](README.md) · [Dokumentasi lengkap dalam bahasa Prancis](../../README.md) · [Dokumentasi lengkap dalam bahasa Inggris](../../README.en.md)

## Fitur

- Mencari PDF yang diizinkan untuk digunakan dan mencantumkan dokumen serta halaman sumber.
- Mengelola koleksi dokumen lokal, riwayat percakapan, dan cadangan.
- Memeriksa hasil retrieval, konteks yang dikirim ke model, dan sumber jawaban.
- Mengevaluasi retrieval dan jawaban dengan dataset Anda sendiri.

## Memulai

Anda memerlukan Python 3.11 atau lebih baru dan Ollama yang berjalan secara lokal. Docker Compose juga tersedia sebagai pilihan. Lihat [panduan instalasi bahasa Prancis](../guide-reproduction.md) atau [panduan bahasa Inggris](../reproduction-guide.en.md) untuk langkah lengkap.

RSLM adalah aplikasi lokal, bukan layanan publik yang di-host. Repositori tidak menyertakan PDF, bobot model, atau indeks. Proses hanya dokumen yang boleh Anda gunakan; jangan commit rahasia `.env` atau data pribadi.

Kode sumber menggunakan lisensi MIT; lisensi ini tidak mencakup dokumen pengguna atau model pihak ketiga. Terjemahan ringkas ini belum ditinjau secara independen oleh penutur asli.
