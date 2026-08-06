#!/usr/bin/env bash
# Enroll ChildMonitor as Android Device Owner (ADB workaround — tanpa factory reset).
# Prasyarat: lihat Blueprint/DEVICE_OWNER_ENROLLMENT.md
set -euo pipefail

PKG="com.example.childmonitor"
ADMIN="${PKG}/.AdminReceiver"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APK_DEBUG="$ROOT/android/ChildMonitor/app/build/outputs/apk/debug/app-debug.apk"
APK_RELEASE="$ROOT/android/ChildMonitor/app/build/outputs/apk/release/app-release.apk"

echo "==> Checking adb devices..."
adb devices
COUNT="$(adb devices | awk 'NR>1 && $2=="device" {c++} END{print c+0}')"
if [[ "$COUNT" -lt 1 ]]; then
  echo "ERROR: Tidak ada perangkat 'device'. Izinkan USB debugging."
  exit 1
fi

echo ""
echo "PENTING (Blueprint 2): Hapus SEMUA akun Google / Mi / Samsung dari HP sebelum lanjut."
echo "Tekan Enter untuk lanjut, atau Ctrl+C untuk batal."
read -r _

APK="$APK_RELEASE"
if [[ ! -f "$APK" ]]; then
  APK="$APK_DEBUG"
fi
if [[ ! -f "$APK" ]]; then
  echo "Building debug APK..."
  (cd "$ROOT/android/ChildMonitor" && ./gradlew assembleDebug)
  APK="$APK_DEBUG"
fi

echo "==> Installing $APK"
adb install -r "$APK"

echo "==> Setting Device Owner: $ADMIN"
if adb shell dpm set-device-owner "$ADMIN"; then
  echo "SUCCESS: Device owner set."
else
  echo "FAILED: Biasanya karena masih ada akun Google/OEM, atau owner sudah diset app lain."
  echo "Coba: Settings > Accounts > hapus semua, lalu ulangi skrip ini."
  exit 1
fi

echo "==> Verify owner"
adb shell dumpsys device_policy 2>/dev/null | grep -A8 -i "device owner" || true

echo "==> Open SetupActivity"
adb shell am start -n "${PKG}/.SetupActivity" || true

echo ""
echo "Selesai. Di setup: isi device_id kanonik (mis. Irfan), URL server always-on, simpan."
echo "Catatan: tanpa factory-reset, hard reset fisik masih bisa menghapus DO."
