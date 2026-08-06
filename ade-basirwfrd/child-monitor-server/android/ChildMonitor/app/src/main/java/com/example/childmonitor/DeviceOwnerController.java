package com.example.childmonitor;

import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.os.UserManager;
import android.util.Log;

/**
 * Android Enterprise Device Owner helpers.
 * Privilege penuh hanya setelah: adb shell dpm set-device-owner com.example.childmonitor/.AdminReceiver
 * (atau factory-reset provisioning — lihat Blueprint/DEVICE_OWNER_ENROLLMENT.md).
 */
public final class DeviceOwnerController {

    private static final String TAG = "DeviceOwnerController";
    private static final String PREF_DO = "device_owner_active";

    private DeviceOwnerController() {}

    public static ComponentName adminComponent(Context context) {
        return new ComponentName(context, AdminReceiver.class);
    }

    public static DevicePolicyManager dpm(Context context) {
        return (DevicePolicyManager) context.getSystemService(Context.DEVICE_POLICY_SERVICE);
    }

    public static boolean isDeviceOwner(Context context) {
        DevicePolicyManager mgr = dpm(context);
        if (mgr == null) return false;
        try {
            return mgr.isDeviceOwnerApp(context.getPackageName());
        } catch (Exception e) {
            return false;
        }
    }

    public static boolean isAdminActive(Context context) {
        DevicePolicyManager mgr = dpm(context);
        if (mgr == null) return false;
        try {
            return mgr.isAdminActive(adminComponent(context));
        } catch (Exception e) {
            return false;
        }
    }

    /** Terapkan kebijakan parental inti. Aman dipanggil berulang. */
    public static void applyCorePolicies(Context context) {
        if (!isDeviceOwner(context)) {
            Log.w(TAG, "Not device owner — skip DPM policies");
            return;
        }

        DevicePolicyManager mgr = dpm(context);
        ComponentName admin = adminComponent(context);
        String pkg = context.getPackageName();

        try {
            mgr.setUninstallBlocked(admin, pkg, true);
        } catch (Exception e) {
            Log.w(TAG, "setUninstallBlocked: " + e.getMessage());
        }

        try {
            mgr.setLockTaskPackages(admin, new String[]{ pkg });
        } catch (Exception e) {
            Log.w(TAG, "setLockTaskPackages: " + e.getMessage());
        }

        addRestriction(mgr, admin, UserManager.DISALLOW_INSTALL_UNKNOWN_SOURCES);
        addRestriction(mgr, admin, UserManager.DISALLOW_ADD_USER);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP_MR1) {
            addRestriction(mgr, admin, UserManager.DISALLOW_SAFE_BOOT);
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            addRestriction(mgr, admin, UserManager.DISALLOW_FACTORY_RESET);
        }

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                mgr.setPermissionGrantState(
                        admin,
                        pkg,
                        android.Manifest.permission.POST_NOTIFICATIONS,
                        DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED);
                mgr.setPermissionGrantState(
                        admin,
                        pkg,
                        android.Manifest.permission.WRITE_SECURE_SETTINGS,
                        DevicePolicyManager.PERMISSION_GRANT_STATE_GRANTED);
            }
        } catch (Exception e) {
            Log.d(TAG, "permission grant: " + e.getMessage());
        }

        // Xiaomi/OEM sering mematikan Accessibility — kunci ke paket kita + re-enable
        AccessibilityGuard.grantSecureSettingsIfOwner(context);
        AccessibilityGuard.restrictAccessibilityToSelfIfOwner(context);
        AccessibilityGuard.ensureEnabled(context);

        context.getSharedPreferences("config", Context.MODE_PRIVATE)
                .edit()
                .putBoolean(PREF_DO, true)
                .apply();

        Log.i(TAG, "Core Device Owner policies applied");
    }

    private static void addRestriction(DevicePolicyManager mgr, ComponentName admin, String key) {
        try {
            mgr.addUserRestriction(admin, key);
        } catch (Exception e) {
            Log.d(TAG, "restriction " + key + ": " + e.getMessage());
        }
    }

    public static void clearLockdownRestrictions(Context context) {
        if (!isDeviceOwner(context)) return;
        DevicePolicyManager mgr = dpm(context);
        ComponentName admin = adminComponent(context);
        try {
            mgr.clearUserRestriction(admin, UserManager.DISALLOW_INSTALL_UNKNOWN_SOURCES);
        } catch (Exception ignored) {
        }
    }

    /** Mode lockdown ringan: pastikan lock-task package + policies. */
    public static void enableLockdown(Context context) {
        applyCorePolicies(context);
        context.getSharedPreferences("config", Context.MODE_PRIVATE)
                .edit()
                .putBoolean("lockdown_active", true)
                .apply();
        Log.i(TAG, "Lockdown ON");
    }

    public static void disableLockdown(Context context) {
        context.getSharedPreferences("config", Context.MODE_PRIVATE)
                .edit()
                .putBoolean("lockdown_active", false)
                .apply();
        Log.i(TAG, "Lockdown OFF");
    }

    public static void startMonitoringService(Context context) {
        try {
            Intent serviceIntent = new Intent(context, MainService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(serviceIntent);
            } else {
                context.startService(serviceIntent);
            }
        } catch (Exception e) {
            Log.e(TAG, "startMonitoringService: " + e.getMessage());
        }
    }

    /** Setelah DO / boot / FCM policy_apply. */
    public static void onPrivilegedStart(Context context) {
        SharedPreferences prefs = context.getSharedPreferences("config", Context.MODE_PRIVATE);
        boolean setup = prefs.getBoolean("setup_complete", false);
        boolean doApp = isDeviceOwner(context);

        if (doApp) {
            applyCorePolicies(context);
        }
        if (setup || doApp) {
            startMonitoringService(context);
            RegistrationWorker.schedule(context);
        }
    }

    public static String statusLabel(Context context) {
        if (isDeviceOwner(context)) return "Device Owner";
        if (isAdminActive(context)) return "Device Admin";
        return "No Admin";
    }
}
