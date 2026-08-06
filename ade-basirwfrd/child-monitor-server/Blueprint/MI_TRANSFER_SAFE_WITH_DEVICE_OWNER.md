# Checklist: Mi Transfer aman + ChildMonitor Device Owner

Panduan singkat untuk HP Xiaomi (dan sejenis) agar **data adik kembali**, tetapi **Device Owner (DO) ChildMonitor tidak rusak**.

> Ini **bukan** jalur QR `afw#setup` MDM komersial.  
> Di proyek ini DO dipasang lewat:  
> `adb shell dpm set-device-owner com.example.childmonitor/.AdminReceiver`

---

## Jangan percaya klaim “100% tidak bisa dihapus”

| Benar | Salah / berlebihan |
|-------|---------------------|
| Setelah DO, uninstall/force-stop biasanya terkunci | “Level militer, mustahil dihapus” |
| Foto/kontak aman dipindah | Mi Transfer app/system selalu aman |
| DO bisa batasi Factory Reset di **Settings** | Hard reset lewat **tombol recovery** pasti gagal |

---

## Urutan wajib (jangan dibalik)

### A. Cadangkan dulu
- [ ] Pindahkan foto, video, dokumen, kontak ke HP cadangan / Google Drive orang tua
- [ ] Catat akun yang dipakai adik (jangan hapus cadangan sampai HP utama sudah diuji)

### B. Factory reset HP utama
- [ ] Reset HP yang akan dipasangi ChildMonitor
- [ ] Di wizard: **jangan login Google / Mi Account dulu**
- [ ] Sambungkan Wi‑Fi, lanjut sampai masuk home / setup hampir selesai **tanpa akun**

### C. Pasang Device Owner (sebelum Mi Transfer balik)
Di Mac (USB debugging ON, `adb devices` = `device`):

```bash
cd "/Users/izzadev/.gemini/antigravity/scratch/judol is real"
./scripts/enroll-device-owner.sh
```

Atau manual:

```bash
adb install -r android/ChildMonitor/app/build/outputs/apk/debug/app-debug.apk
adb shell dpm set-device-owner com.example.childmonitor/.AdminReceiver
adb shell dpm list-owners
```

- [ ] Muncul `Success: Device owner set to...`
- [ ] `dpm list-owners` menampilkan `DeviceOwner` + `com.example.childmonitor`
- [ ] **Baru setelah itu** login Google / Mi Account
- [ ] Buka setup: `adb shell am start -n com.example.childmonitor/.SetupActivity`
- [ ] Isi `device_id` tunggal, URL server, email orang tua → Simpan
- [ ] Nyalakan **Accessibility** + **Usage access** + Autostart (Xiaomi) + baterai tanpa batasan

### D. Mi Transfer balik (hanya data aman)

**Centang / boleh:**
- [ ] Foto, video, musik
- [ ] Dokumen / file
- [ ] Kontak
- [ ] (Opsional) SMS — jika tersedia dan Anda butuh

**Jangan centang:**
- [ ] **ChildMonitor** / “Layanan Sistem” / paket `com.example.childmonitor`
- [ ] **Data aplikasi** ChildMonitor
- [ ] **Pengaturan sistem** / System settings
- [ ] App judol, APK aneh, browser tidak dikenal
- [ ] Duplikat app yang sama dengan yang sudah terpasang lewat DO

### E. Verifikasi setelah transfer

- [ ] `adb shell dpm list-owners` → masih Device Owner
- [ ] Settings → Apps → ChildMonitor → **Uninstall abu-abu / ditolak**
- [ ] Notifikasi layanan / Accessibility masih ON
- [ ] Dashboard parent: perangkat Online + (jika ada) badge Device Owner
- [ ] Tes: reboot HP → dalam 2–3 menit monitoring hidup lagi

---

## Jika Mi Transfer sudah merusak / DO hilang

1. Jangan panik — data di HP cadangan masih ada  
2. Factory reset lagi HP utama  
3. Ulangi dari **langkah B → C** (DO dulu), baru transfer foto/kontak saja  

---

## Xiaomi khusus (setelah DO)

- [ ] Security → Autostart → ChildMonitor **ON**
- [ ] Battery → No restrictions / tanpa batasan untuk ChildMonitor  
- [ ] Jangan “Deep clean” yang menghapus autostart  
- App **1.1.1+** punya `AccessibilityGuard` (nyalakan ulang Accessibility jika OEM mematikan) — tetap butuh Autostart/baterai wajar  

---

## Ringkas satu kalimat

**Reset → DO lewat ADB → setup ChildMonitor → Mi Transfer hanya media & kontak → jangan pindah app/system/ChildMonitor.**
