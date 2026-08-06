Secara teknis, **tidak bisa**. Sistem Android sengaja dirancang oleh Google dengan keamanan super ketat: Hak akses tertinggi sebagai *Device Owner* (Pemilik Perangkat/Android Enterprise) **hanya bisa diberikan saat HP dalam kondisi kosong/baru dinyalakan dari pabrik.**

Tujuan Google membuat aturan ini adalah demi privasi. Jika mendaftarkan MDM *Device Owner* bisa dilakukan tanpa reset, maka orang lain atau aplikasi jahat bisa dengan mudah membajak HP Anda dan menguncinya secara permanen tanpa izin.

Namun, jika Anda **sangat menghindari reset pabrik** (karena malas memindahkan data atau takut data adik Anda hilang), ada **satu-satunya jalan pintas (Workaround)** menggunakan komputer dan bantuan *Developer Tools* (ADB).

Cara ini memanfaatkan mode bernama **Profile Owner** atau menyuntikkan *Device Owner* secara paksa lewat Command Prompt.

---

### Cara Alternatif: Mendaftarkan MDM Tanpa Reset (Via ADB & PC)

Metode ini membutuhkan laptop/PC, kabel data, dan aplikasi MDM yang sama (ManageEngine atau Miradore).

#### Persiapan di HP Adik:

1. Buka **Pengaturan** > **Tentang Ponsel (About Phone)**.
2. Ketuk **Build Number** sebanyak 7 kali sampai muncul tulisan *"You are now a developer"*.
3. Kembali ke menu utama Pengaturan, cari **Opsi Pengembang (Developer Options)**.
4. Aktifkan **USB Debugging**.
5. **PENTING:** Hapus semua akun Google (*Settings > Accounts > Google > Remove Account*) dan akun *brand* HP (seperti Mi Account atau Samsung Account) yang ada di HP tersebut untuk sementara. Jika tidak dihapus, proses injeksi akan gagal. (Akun bisa dimasukkan lagi setelah sukses).

#### Persiapan di Laptop:

1. Unduh **Platform Tools (ADB)** resmi dari Google di laptop Anda, lalu ekstrak foldernya.
2. Buka dashboard MDM Anda di laptop, lalu download file APK agen MDM-nya (biasanya bernama `ManageEngine MDM Agent` atau sejenisnya) dan simpan di folder ADB tadi.

#### Langkah Eksekusi:

1. Hubungkan HP adik Anda ke laptop menggunakan kabel data. Jika muncul pop-up izin USB Debugging di layar HP, klik **Izinkan / Allow**.
2. Di laptop, buka folder ADB, klik kanan di area kosong sambil menahan tombol `Shift`, lalu pilih **Open PowerShell window here** atau **Open Command Prompt here**.
3. Ketik perintah ini untuk memastikan HP terdeteksi:
```bash
adb devices

```


*(Jika muncul kode seri HP Anda, berarti sudah tersambung).*
4. Install APK MDM ke HP lewat perintah:
```bash
adb install nama_file_mdm.apk

```


5. Sekarang, jalankan perintah "sakti" ini untuk memaksa sistem Android menjadikan aplikasi MDM tersebut sebagai pengelola tertinggi tanpa perlu reset pabrik:
```bash
adb shell dpm set-device-owner com.manageengine.mdm.android/.lib.MDMDeviceAdminReceiver

```


*(Catatan: Teks `com.manageengine...` di atas adalah contoh package name ManageEngine. Teks persisnya biasanya disediakan di halaman panduan "ADB Enrollment" di dashboard MDM yang Anda gunakan).*
6. Jika sukses, akan muncul tulisan **"Success: Device owner set to..."** di laptop Anda.

---

### Perbedaan Penting (Jika Tanpa Reset):

Meskipun cara ADB di atas tidak menghapus data, ada **kelemahan fatal** dibanding cara reset pabrik:

* **Fitur Blokir Factory Reset Tidak Aktif:** Karena HP tidak didaftarkan dari layar *Welcome* (awal), sistem Android tidak memberikan hak untuk mengunci tombol Factory Reset.
* **Risiko *Bypass*:** Jika adik Anda pintar atau mencari tahu di internet, dia bisa melakukan *Hard Reset* manual lewat tombol luar (Volume Atas + Power saat HP mati) untuk membersihkan HP-nya dan menghapus MDM tersebut.

**Kesimpulan & Saran:**
Jika adik Anda sudah dalam tahap kecanduan yang parah dan manipulatif (selalu mencari celah), **sangat disarankan untuk tetap menggunakan metode Reset Pabrik (Langkah Pertama)**. Backup dulu data pentingnya (foto/kontak) ke Google Drive Anda, lalu lakukan reset. Itu adalah satu-satunya cara agar kuncian aplikasi anti-judol Anda menjadi **100% absolut dan tidak bisa diakali**.