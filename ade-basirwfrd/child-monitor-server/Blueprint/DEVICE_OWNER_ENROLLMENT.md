# Device Owner Enrollment — ChildMonitor

ChildMonitor dapat menjadi **Android Enterprise Device Owner** (MDM tingkat sistem), bukan hanya Device Admin biasa. Ini mengurangi force-close / uninstall oleh anak dan memperkuat auto-start setelah reboot.

## Dua jalur

| Jalur | Kapan | Factory reset terkunci? |
|-------|--------|-------------------------|
| **A. ADB** (`dpm set-device-owner`) | Cepat, data HP tidak dihapus | **Tidak** — hard reset fisik masih bisa |
| **B. Factory reset + enroll** | Anak manipulatif / butuh kunci absolut | **Ya** (mendekati absolut) |

Detail teoritis: [blueprint 2.md](blueprint%202.md).

---

## Jalur A — ADB (tanpa reset)

### Di HP anak

1. Aktifkan **Opsi pengembang** → **USB debugging**.
2. **Hapus semua akun** Google, Mi Account, Samsung Account, dll. (`Settings > Accounts`).
3. Pastikan belum ada Device Owner lain.

### Di Mac/PC

```bash
chmod +x scripts/enroll-device-owner.sh
./scripts/enroll-device-owner.sh
```

Atau manual:

```bash
adb install -r android/ChildMonitor/app/build/outputs/apk/debug/app-debug.apk
adb shell dpm set-device-owner com.example.childmonitor/.AdminReceiver
adb shell am start -n com.example.childmonitor/.SetupActivity
adb shell dumpsys device_policy | grep -A5 -i owner
```

Sukses: `Success: Device owner set to...`

### Setelah enroll

1. Buka setup → `device_id` tunggal (hindari duplikat `Irfan`/`irfan`).
2. URL server = **always-on** (Fly/Railway), bukan HF yang sleep — lihat [backend/DEPLOY_ALWAYS_ON.md](../backend/DEPLOY_ALWAYS_ON.md).
3. Izinkan Usage Access + Accessibility.
4. Dashboard: badge **Device Owner**; tombol **Terapkan policy**.

Policy yang diterapkan app: blok uninstall paket sendiri, batasi unknown sources / safe boot / add user / factory reset (sejauh diizinkan jalur enroll), lock-task package.

---

## Jalur B — Factory reset (kunci absolut)

1. Backup foto/kontak anak ke Google Drive **orang tua**.
2. Factory reset HP.
3. Di layar **Welcome**: **jangan** login Google / akun OEM dulu.
4. Aktifkan USB debugging (bisa lewat opsi pengembang di setup wizard atau setelah skip akun — ikuti OEM).
5. Jalankan `./scripts/enroll-device-owner.sh` **sebelum** menambah akun Google.
6. Baru setelah `Success: Device owner set`: login akun, setup ChildMonitor, a11y/usage.
7. Verifikasi: uninstall app dari Settings harus **ditolak**.

Ini satu-satunya jalur yang mendekati “tidak bisa diakali” untuk factory reset dari Settings + FRP enterprise.

---

## Hapus Device Owner (hanya orang tua / debug)

Device Owner biasanya **tidak bisa** dihapus dari UI. Untuk lab:

```bash
adb shell dpm remove-active-admin com.example.childmonitor/.AdminReceiver
```

(Beberapa versi Android menolak remove kecuali factory reset.)

---

## Backend & dashboard

1. Deploy always-on + set `PUBLIC_BASE_URL`.
2. Jalankan SQL: [backend/sql/devices_health_columns.sql](../backend/sql/devices_health_columns.sql).
3. Online = heartbeat &lt; **10 menit** (bukan 24 jam).
4. Rapikan duplikat lewat tombol **Hapus baris** di dashboard.
