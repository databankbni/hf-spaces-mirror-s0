package com.example.childmonitor;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.os.Build;
import android.provider.Settings;
import android.text.TextUtils;
import android.util.Log;
import android.view.accessibility.AccessibilityManager;

import java.util.Collections;
import java.util.List;

/**
 * Menjaga URLMonitoringService tetap aktif.
 * Android tidak mengizinkan "kunci toggle" Accessibility secara resmi,
 * tapi Device Owner bisa: (1) grant WRITE_SECURE_SETTINGS, (2) menulis ulang
 * ENABLED_ACCESSIBILITY_SERVICES, (3) batasi layanan a11y lain (Xiaomi sering matikan).
 */
public final class AccessibilityGuard {

    private static final String TAG = "AccessibilityGuard";

    private AccessibilityGuard() {}

    public static ComponentName serviceComponent(Context context) {
        return new ComponentName(context, URLMonitoringService.class);
    }

    public static String flattenComponent(Context context) {
        return serviceComponent(context).flattenToString();
    }

    public static boolean isOurServiceEnabled(Context context) {
        ComponentName want = serviceComponent(context);
        AccessibilityManager am =
                (AccessibilityManager) context.getSystemService(Context.ACCESSIBILITY_SERVICE);
        if (am != null) {
            List<AccessibilityServiceInfo> list =
                    am.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_ALL_MASK);
            if (list != null) {
                for (AccessibilityServiceInfo info : list) {
                    if (info == null || info.getResolveInfo() == null
                            || info.getResolveInfo().serviceInfo == null) {
                        continue;
                    }
                    ComponentName cn = new ComponentName(
                            info.getResolveInfo().serviceInfo.packageName,
                            info.getResolveInfo().serviceInfo.name);
                    if (cn.equals(want)) return true;
                }
            }
        }
        // Fallback Settings.Secure
        try {
            String enabled = Settings.Secure.getString(
                    context.getContentResolver(),
                    Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
            if (enabled == null) return false;
            TextUtils.SimpleStringSplitter splitter = new TextUtils.SimpleStringSplitter(':');
            splitter.setString(enabled);
            String flat = want.flattenToString();
            String shortFlat = want.flattenToShortString();
            while (splitter.hasNext()) {
                String item = splitter.next();
                if (flat.equalsIgnoreCase(item) || shortFlat.equalsIgnoreCase(item)) {
                    return true;
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "isOurServiceEnabled: " + e.getMessage());
        }
        return false;
    }

    /** Grant izin tulis secure settings (hanya Device Owner). */
    public static void grantSecureSettingsIfOwner(Context context) {
        if (!DeviceOwnerController.isDeviceOwner(context)) return;
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return;
        try {
            DevicePolicyManager mgr = DeviceOwnerController.dpm(context);
            ComponentName admin = DeviceOwnerController.adminComponent(context);
            mgr.setPermissionGrantState(
                    admin,
                    context.getPackageName(),
                    android.Manifest.permission.WRITE_SECURE_SETTINGS,
                    DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED);
            Log.i(TAG, "WRITE_SECURE_SETTINGS granted via DO");
        } catch (Exception e) {
            Log.w(TAG, "grantSecureSettings: " + e.getMessage());
        }
    }

    /**
     * Hanya izinkan Accessibility dari paket kita (DO).
     * Mengurangi gangguan layanan a11y lain / reset OEM.
     */
    public static void restrictAccessibilityToSelfIfOwner(Context context) {
        if (!DeviceOwnerController.isDeviceOwner(context)) return;
        try {
            DevicePolicyManager mgr = DeviceOwnerController.dpm(context);
            ComponentName admin = DeviceOwnerController.adminComponent(context);
            mgr.setPermittedAccessibilityServices(
                    admin, Collections.singletonList(context.getPackageName()));
            Log.i(TAG, "Permitted accessibility services = self only");
        } catch (Exception e) {
            Log.w(TAG, "setPermittedAccessibilityServices: " + e.getMessage());
        }
    }

    /**
     * Paksa nyalakan layanan kita lewat Settings.Secure.
     * @return true jika terlihat enabled setelah percobaan
     */
    public static boolean forceEnableOurService(Context context) {
        grantSecureSettingsIfOwner(context);
        String flat = flattenComponent(context);
        try {
            String current = Settings.Secure.getString(
                    context.getContentResolver(),
                    Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES);
            if (current == null) current = "";

            boolean already = false;
            TextUtils.SimpleStringSplitter splitter = new TextUtils.SimpleStringSplitter(':');
            splitter.setString(current);
            StringBuilder sb = new StringBuilder();
            while (splitter.hasNext()) {
                String item = splitter.next();
                if (item == null || item.isEmpty()) continue;
                if (flat.equalsIgnoreCase(item)
                        || serviceComponent(context).flattenToShortString().equalsIgnoreCase(item)) {
                    already = true;
                }
                if (sb.length() > 0) sb.append(':');
                sb.append(item);
            }
            if (!already) {
                if (sb.length() > 0) sb.append(':');
                sb.append(flat);
            }

            boolean putOk = Settings.Secure.putString(
                    context.getContentResolver(),
                    Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
                    sb.toString());
            Settings.Secure.putInt(
                    context.getContentResolver(),
                    Settings.Secure.ACCESSIBILITY_ENABLED,
                    1);
            Log.i(TAG, "forceEnable putOk=" + putOk + " list=" + sb);
        } catch (SecurityException se) {
            Log.e(TAG, "forceEnable needs WRITE_SECURE_SETTINGS / Device Owner: " + se.getMessage());
            return false;
        } catch (Exception e) {
            Log.e(TAG, "forceEnable: " + e.getMessage());
            return false;
        }
        return isOurServiceEnabled(context);
    }

    /**
     * Panggil berkala dari MainService: jika dimatikan OEM/Xiaomi → nyalakan lagi.
     * @return true jika service aktif setelah ensure
     */
    public static boolean ensureEnabled(Context context) {
        if (isOurServiceEnabled(context)) {
            return true;
        }
        Log.w(TAG, "Accessibility OFF — attempting re-enable (Xiaomi/OEM guard)");
        restrictAccessibilityToSelfIfOwner(context);
        boolean ok = forceEnableOurService(context);
        if (!ok) {
            Log.e(TAG, "Re-enable failed — user must open Accessibility settings once, or enroll Device Owner");
        }
        return ok;
    }
}
