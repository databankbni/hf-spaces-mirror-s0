package com.example.childmonitor;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import android.util.Log;

import java.util.Arrays;
import java.util.List;

/**
 * Membuka layar pengaturan baterai/autostart per OEM agar layanan tidak dibunuh (Samsung, Xiaomi, OPPO, Vivo, Huawei).
 * Beberapa merek punya banyak varian (MIUI/Global, ColorOS/Oplus); dicoba berurutan.
 */
public final class OemPowerSetupHelper {

    private static final String TAG = "OemPowerSetupHelper";

    private OemPowerSetupHelper() {}

    /** Panggil dari SetupActivity setelah izin baterai standar. */
    public static void openManufacturerPowerSettings(Context context) {
        String m = Build.MANUFACTURER != null ? Build.MANUFACTURER.toLowerCase() : "";

        if (m.contains("xiaomi") || m.contains("redmi") || m.contains("poco")) {
            tryOpenXiaomiAutostart(context);
        }
        if (m.contains("samsung")) {
            tryOpenSamsungBattery(context);
        }
        if (m.contains("oppo") || m.contains("realme") || m.contains("oneplus")) {
            tryOpenOppoRealmeStartup(context);
        }
        if (m.contains("vivo")) {
            tryOpenVivoStartup(context);
        }
        if (m.contains("huawei") || m.contains("honor")) {
            tryOpenHuaweiBattery(context);
        }
        tryOpenAppDetails(context);
    }

    private static void startComponent(Context context, String pkg, String cls) {
        try {
            Intent i = new Intent();
            i.setComponent(new ComponentName(pkg, cls));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(i);
            Log.d(TAG, "Opened " + pkg + "/" + cls);
        } catch (Exception e) {
            Log.d(TAG, "Skip " + cls + ": " + e.getMessage());
        }
    }

    private static void tryOpenXiaomiAutostart(Context context) {
        List<String[]> pages = Arrays.asList(
                new String[]{"com.miui.securitycenter", "com.miui.permcenter.autostart.AutoStartManagementActivity"},
                new String[]{"com.miui.securitycenter", "com.miui.powercenter.PowerSettings"},
                new String[]{"com.miui.securitycenter", "com.miui.powercenter.ui.PowerMainActivity"},
                new String[]{"com.miui.securitycenter", "com.miui.appmanager.AppManagerMainActivity"}
        );
        for (String[] p : pages) {
            startComponent(context, p[0], p[1]);
        }
    }

    /** Samsung: Smart Manager / penghemat baterai per app */
    private static void tryOpenSamsungBattery(Context context) {
        try {
            Intent i = new Intent();
            i.setComponent(new ComponentName(
                    "com.samsung.android.lool",
                    "com.samsung.android.sm.ui.battery.BatteryActivity"));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(i);
            Log.d(TAG, "Opened Samsung battery");
        } catch (Exception e1) {
            try {
                Intent i2 = new Intent("com.samsung.android.sm.ACTION_APP_BATTERY_SETTINGS");
                i2.setData(Uri.parse("package:" + context.getPackageName()));
                i2.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(i2);
            } catch (Exception e2) {
                Log.d(TAG, "Samsung battery: " + e2.getMessage());
            }
        }
    }

    /** OPPO / Realme / OnePlus — ColorOS & Oplus: autostart + batas latar */
    private static void tryOpenOppoRealmeStartup(Context context) {
        List<String[]> pages = Arrays.asList(
                new String[]{"com.coloros.safecenter", "com.coloros.safecenter.permission.startup.StartupAppListActivity"},
                new String[]{"com.oplus.safecenter", "com.oplus.safecenter.startupapp.StartupAppListActivity"},
                new String[]{"com.oplus.safecenter", "com.oplus.safecenter.permission.startup.StartupAppListActivity"},
                new String[]{"com.coloros.oppoguardelf", "com.coloros.powermanager.fuelgaue.PowerConsumptionActivity"},
                new String[]{"com.oplus.battery", "com.oplus.battery.OplusBatteryActivity"}
        );
        for (String[] p : pages) {
            startComponent(context, p[0], p[1]);
        }
    }

    private static void tryOpenVivoStartup(Context context) {
        List<String[]> pages = Arrays.asList(
                new String[]{"com.iqoo.secure", "com.iqoo.secure.ui.phoneoptimize.BgStartUpManager"},
                new String[]{"com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.BgStartUpManagerActivity"},
                new String[]{"com.iqoo.secure", "com.iqoo.secure.ui.phoneoptimize.AddWhiteListActivity"},
                new String[]{"com.vivo.permissionmanager", "com.vivo.permissionmanager.activity.SoftPermissionDetailActivity"}
        );
        for (String[] p : pages) {
            startComponent(context, p[0], p[1]);
        }
    }

    private static void tryOpenHuaweiBattery(Context context) {
        try {
            Intent i = new Intent();
            i.setComponent(new ComponentName(
                    "com.huawei.systemmanager",
                    "com.huawei.systemmanager.startupmgr.ui.StartupNormalAppListActivity"));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(i);
            Log.d(TAG, "Opened Huawei startup");
        } catch (Exception e) {
            Log.d(TAG, "Huawei: " + e.getMessage());
        }
    }

    private static void tryOpenAppDetails(Context context) {
        try {
            Intent i = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
            i.setData(Uri.parse("package:" + context.getPackageName()));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(i);
        } catch (Exception e) {
            Log.d(TAG, "App details: " + e.getMessage());
        }
    }
}
