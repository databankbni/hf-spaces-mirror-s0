# Cara pasang aset brand ke template Konten IG

Template konten Instagram sekarang **ber-brand** (logo, headline highlight, tombol CTA, footer kontak, dots) — mirip referensi loggerindo. Brand diatur di **`agent-konten-ig/konten-ig.html`** pada objek `BRAND` (di dalam `<script>`, dekat atas):

```js
var BRAND = {
  name: "LOGGERINDO",
  logoUrl: "",                 // URL logo PNG transparan (kosong = pakai teks nama)
  navy: "#12294d",             // warna utama (gelap)
  gold: "#f2b705",             // warna highlight & tombol CTA
  textOnGold: "#12294d",       // warna teks di tombol CTA
  contact: { phone:"0852-8571-1081", email:"sales@taharica.com", web:"loggerindo.com" }
};
```

## 1) Logo
- Taruh file logo (PNG transparan) di folder ini: `agent-konten-ig/brand/`
- Setelah ke-push ke GitHub, `logoUrl` diisi URL raw-nya, contoh:
  `https://raw.githubusercontent.com/Alfaza-R/ai-agent/main/agent-konten-ig/brand/logo.png`
- Kalau `logoUrl` kosong → template pakai **teks nama** (`name`) di badge putih.

## 2) Warna & font
- Ganti `navy` (warna utama) & `gold` (highlight + tombol) sesuai brand.
- Font default Poppins. Kalau mau font brand khusus, kabari — bisa di-embed.

## 3) Kontak footer
- Edit `contact.phone / email / web`.

Setelah edit `BRAND`, **re-paste** `konten-ig.html` ke halaman WP → Update → Ctrl+F5.
