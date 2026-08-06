# Rapikan duplikat device (Irfan / irfan / anak1)

1. Buka dashboard always-on → tab **Perangkat**.
2. Identifikasi baris dengan heartbeat terbaru (itu yang dipakai HP).
3. Untuk baris lama/duplikat: klik **Hapus baris**.
4. Atau API:
   ```bash
   curl -X DELETE "https://YOUR-HOST/api/devices/irfan"
   ```
5. Di HP: pastikan `device_id` di setup **persis** sama dengan baris yang dipertahankan.
