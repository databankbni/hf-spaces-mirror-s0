# Cara upload gambar (aset & referensi)

Agent Konten IG membaca gambar dari **2 folder di repo GitHub ini** setiap kali dijalankan:

| Folder | Isi | Dipakai untuk |
|---|---|---|
| `agent-konten-ig/aset/` | Foto/aset milikmu (produk, logo, foto orang, dll) | **ditempel** ke layout oleh Agent Layouting |
| `agent-konten-ig/referensi/` | Contoh design yang jadi acuan gaya | **dibandingkan** oleh Agent Checker Visual |

Format yang didukung: **.png .jpg .jpeg .webp**

## Cara nambah gambar (paling gampang — lewat web GitHub)
1. Buka repo: `https://github.com/Alfaza-R/ai-agent`
2. Masuk ke folder `agent-konten-ig/aset/` (atau `referensi/`).
3. Klik **Add file → Upload files** → drag gambar → **Commit changes**.
4. Selesai. Agent langsung pakai gambar terbaru di run berikutnya (tidak perlu re-deploy).

## Cara lewat git (kalau di komputer)
```
# taruh gambar ke folder, lalu:
git add agent-konten-ig/aset agent-konten-ig/referensi
git commit -m "tambah aset/referensi konten IG"
git push origin main
```

## Catatan
- Repo harus **public** (sudah public) supaya backend bisa baca tanpa token.
- Nama file dipakai Agent Layouting untuk memilih aset — beri nama yang deskriptif (mis. `produk-orion.png`, `foto-lab.jpg`).
- Kalau mau pindah ke repo/branch lain, set Secret `KONTEN_GH_REPO` / `KONTEN_GH_BRANCH` di HF Space.
- File `.gitkeep` cuma penanda folder, boleh diabaikan.
