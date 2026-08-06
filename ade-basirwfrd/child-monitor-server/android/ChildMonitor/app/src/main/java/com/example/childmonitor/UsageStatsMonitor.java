package com.example.childmonitor;

import android.app.usage.UsageStats;
import android.app.usage.UsageStatsManager;
import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.os.Build;

import java.util.List;
import java.util.SortedMap;
import java.util.TreeMap;

public class UsageStatsMonitor {

    /**
     * Get the currently foreground app package name
     * @param context Application context
     * @return Package name of the foreground app, or empty string
     */
    public static String getForegroundApp(Context context) {
        String currentApp = null;

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            UsageStatsManager usm = (UsageStatsManager) context.getSystemService(Context.USAGE_STATS_SERVICE);
            if (usm == null) return "";

            long time = System.currentTimeMillis();
            List<UsageStats> stats = usm.queryUsageStats(
                    UsageStatsManager.INTERVAL_DAILY,
                    time - 1000 * 60, // Last 1 minute
                    time
            );

            if (stats != null && !stats.isEmpty()) {
                SortedMap<Long, UsageStats> sortedMap = new TreeMap<>();
                for (UsageStats usageStats : stats) {
                    sortedMap.put(usageStats.getLastTimeUsed(), usageStats);
                }
                if (!sortedMap.isEmpty()) {
                    currentApp = sortedMap.get(sortedMap.lastKey()).getPackageName();
                }
            }
        }

        return currentApp != null ? currentApp : "";
    }

    /**
     * Get the human-readable label for a package
     * @param context Application context
     * @param packageName Package name
     * @return App label or the package name itself
     */
    public static String getAppLabel(Context context, String packageName) {
        try {
            PackageManager pm = context.getPackageManager();
            ApplicationInfo ai = pm.getApplicationInfo(packageName, 0);
            return pm.getApplicationLabel(ai).toString();
        } catch (PackageManager.NameNotFoundException e) {
            return packageName;
        }
    }
}
