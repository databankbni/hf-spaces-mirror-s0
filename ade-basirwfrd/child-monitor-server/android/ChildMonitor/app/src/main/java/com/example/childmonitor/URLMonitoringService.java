package com.example.childmonitor;

import android.accessibilityservice.AccessibilityService;
import android.app.admin.DevicePolicyManager;
import android.content.BroadcastReceiver;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.os.Build;
import android.util.Log;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

public class URLMonitoringService extends AccessibilityService {

    private static final String TAG = "URLMonitor";

    // Map of known browser packages to their URL bar resource IDs
    private static final Map<String, String> BROWSER_URL_BAR_IDS = new HashMap<>();
    static {
        BROWSER_URL_BAR_IDS.put("com.android.chrome", "com.android.chrome:id/url_bar");
        BROWSER_URL_BAR_IDS.put("com.chrome.beta", "com.android.chrome:id/url_bar");
        BROWSER_URL_BAR_IDS.put("org.mozilla.firefox", "org.mozilla.firefox:id/url_bar_title");
        BROWSER_URL_BAR_IDS.put("org.mozilla.firefox_beta", "org.mozilla.firefox_beta:id/url_bar_title");
        BROWSER_URL_BAR_IDS.put("org.mozilla.focus", "org.mozilla.focus:id/url_view");
        BROWSER_URL_BAR_IDS.put("com.opera.browser", "com.opera.browser:id/url_field");
        BROWSER_URL_BAR_IDS.put("com.opera.mini.native", "com.opera.mini.native:id/url_field");
        BROWSER_URL_BAR_IDS.put("com.brave.browser", "com.brave.browser:id/url_bar");
        BROWSER_URL_BAR_IDS.put("com.duckduckgo.mobile.android", "com.duckduckgo.mobile.android:id/omnibarTextInput");
        BROWSER_URL_BAR_IDS.put("com.microsoft.emmx", "com.microsoft.emmx:id/url_bar");
        BROWSER_URL_BAR_IDS.put("com.UCMobile.intl", "com.UCMobile.intl:id/address_editor_with_progress");
        BROWSER_URL_BAR_IDS.put("com.sec.android.app.sbrowser", "com.sec.android.app.sbrowser:id/location_bar_edit_text");
    }

    private String lastUrl = "";
    private SharedPreferences prefs;
    private boolean isQuizActive = false;

    private final BroadcastReceiver quizReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            if ("LAUNCH_QUIZ_INTERNAL".equals(intent.getAction())) {
                Log.d(TAG, "Launching Quiz via Accessibility bypass");
                isQuizActive = true;
                Intent quizIntent = new Intent(context, QuizActivity.class);
                quizIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                startActivity(quizIntent);
            } else if ("STOP_QUIZ".equals(intent.getAction())) {
                Log.d(TAG, "Quiz stopped, disabling shield");
                isQuizActive = false;
            }
        }
    };

    @Override
    public void onServiceConnected() {
        super.onServiceConnected();
        prefs = getSharedPreferences("config", MODE_PRIVATE);
        
        IntentFilter filter = new IntentFilter();
        filter.addAction("LAUNCH_QUIZ_INTERNAL");
        filter.addAction("STOP_QUIZ");

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            registerReceiver(quizReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(quizReceiver, filter);
        }
        Log.d(TAG, "✅ Service CONNECTED and running!");

        // Sync blocklist from server immediately
        JudiFilter.syncBlocklist(this);

        // Remote debug log
        String deviceId = prefs.getString("device_id", "Unknown");
        RetrofitClient.getInstance(this).sendErrorLog(new ErrorLogRequest(
                deviceId, "INFO", "Accessibility Service Connected", "", "URLMonitor"
        )).enqueue(new Callback<Void>() {
            @Override
            public void onResponse(Call<Void> call, Response<Void> response) {}
            @Override
            public void onFailure(Call<Void> call, Throwable t) {}
        });
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null) return;

        // ACCESSIBILITY SHIELD: If quiz is active, prevent leaving
        if (isQuizActive && event.getEventType() == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            String pkg = event.getPackageName() != null ? event.getPackageName().toString() : "";
            if (!pkg.isEmpty() && !pkg.equals(getPackageName())) {
                Log.d(TAG, "Quiz Shield: Blocking transition to " + pkg);
                Intent intent = new Intent(this, QuizActivity.class);
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_REORDER_TO_FRONT);
                startActivity(intent);
                return; 
            }
        }

        if (event.getPackageName() == null) return;
        int eventType = event.getEventType();
        if (eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED &&
                eventType != AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED) {
            return;
        }

        String packageName = event.getPackageName().toString();

        if (isBrowser(packageName)) {
            AccessibilityNodeInfo root = getRootInActiveWindow();
            if (root == null) {
                root = event.getSource();
            }
            if (root == null) return;

            String url = findUrlFromRoot(root, packageName);
            if (url != null && !url.isEmpty()) {
                // Clean the URL
                String cleanUrl = url.trim()
                        .replaceAll("^https?://", "")
                        .replaceAll("^www\\.", "");

                boolean isJudi = JudiFilter.isJudiSite(cleanUrl);

                if (isJudi) {
                    // ALWAYS block judi URLs — even on repeat visits
                    Log.d(TAG, "🚨 JUDI DETECTED: " + cleanUrl);
                    sendUrlLog(packageName, cleanUrl, true);
                    handleJudiDetected(cleanUrl);
                    lastUrl = cleanUrl;
                } else if (!cleanUrl.equals(lastUrl)) {
                    // Non-judi: log only on URL change
                    lastUrl = cleanUrl;
                    Log.d(TAG, "📝 URL logged: " + cleanUrl);
                    sendUrlLog(packageName, cleanUrl, false);
                }
            }
        }
    }

    private boolean isBrowser(String packageName) {
        return packageName.contains("browser") ||
                packageName.contains("chrome") ||
                packageName.contains("firefox") ||
                packageName.contains("opera") ||
                packageName.contains("brave") ||
                packageName.contains("duckduckgo") ||
                packageName.contains("sbrowser") ||
                packageName.contains("UCMobile") ||
                packageName.contains("kiwi") ||
                packageName.contains("via") ||
                BROWSER_URL_BAR_IDS.containsKey(packageName);
    }

    private String findUrlFromRoot(AccessibilityNodeInfo root, String packageName) {
        if (root == null) return null;

        // 1. Try Chrome-specific IDs
        if (packageName.equals("com.android.chrome")) {
            String[] chromeIds = {
                    "com.android.chrome:id/url_bar",
                    "com.android.chrome:id/location_bar_edit_text",
                    "com.android.chrome:id/search_box_text",
                    "com.android.chrome:id/url_text",
                    "com.android.chrome:id/url_edit_text",
                    "com.android.chrome:id/line_1",
                    "com.android.chrome:id/line_2"
            };
            for (String id : chromeIds) {
                List<AccessibilityNodeInfo> nodes = root.findAccessibilityNodeInfosByViewId(id);
                if (nodes != null && !nodes.isEmpty()) {
                    CharSequence text = nodes.get(0).getText();
                    if (isValidUrl(text)) {
                        Log.d(TAG, "Found URL via Chrome ID [" + id + "]: " + text);
                        return text.toString().trim();
                    }
                }
            }
        }

        // 2. Try browser-specific ID from map
        if (BROWSER_URL_BAR_IDS.containsKey(packageName)) {
            String barId = BROWSER_URL_BAR_IDS.get(packageName);
            List<AccessibilityNodeInfo> nodes = root.findAccessibilityNodeInfosByViewId(barId);
            if (nodes != null && !nodes.isEmpty()) {
                CharSequence text = nodes.get(0).getText();
                if (isValidUrl(text)) {
                    Log.d(TAG, "Found URL via browser map [" + barId + "]: " + text);
                    return text.toString().trim();
                }
            }
        }

        // 3. Generic search for common address bar IDs
        String[] genericIds = {
                "url_bar", "address_bar", "location_bar", "url_edit_text",
                "search_src_text", "omnibar", "address_edit_text", "url_field"
        };
        for (String gid : genericIds) {
            List<AccessibilityNodeInfo> nodes = root.findAccessibilityNodeInfosByViewId(packageName + ":id/" + gid);
            if (nodes != null && !nodes.isEmpty()) {
                CharSequence text = nodes.get(0).getText();
                if (isValidUrl(text)) {
                    Log.d(TAG, "Found URL via generic ID [" + gid + "]: " + text);
                    return text.toString().trim();
                }
            }
        }

        // 4. Fallback: search for EditText ONLY (address bars are EditText, not TextView)
        return findAddressBarFallback(root);
    }

    /**
     * STRICT URL validation — only accept actual URLs, not page content.
     */
    private boolean isValidUrl(CharSequence text) {
        if (text == null) return false;
        String t = text.toString().trim();
        if (t.isEmpty()) return false;
        if (t.length() < 4 || t.length() > 2000) return false;

        // REJECT anything with spaces — real URLs NEVER have spaces
        if (t.contains(" ")) return false;

        // REJECT timestamps like 08:12
        if (t.matches("^[0-9]+[:.][0-9]+$")) return false;

        // Must contain a dot followed by at least 2 letters (domain TLD pattern)
        return t.matches(".*\\.[a-zA-Z]{2,}.*");
    }

    /**
     * Fallback: find EditText with URL content.
     * IMPORTANT: Only scan EditText (address bars), NOT TextView (page content)!
     */
    private String findAddressBarFallback(AccessibilityNodeInfo node) {
        if (node == null) return null;

        // ONLY EditText — address bars are always EditText
        if ("android.widget.EditText".equals(node.getClassName())) {
            if (isValidUrl(node.getText())) {
                Log.d(TAG, "Found URL via EditText fallback: " + node.getText());
                return node.getText().toString();
            }
        }

        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                String result = findAddressBarFallback(child);
                if (result != null) return result;
            }
        }

        return null;
    }

    private void sendUrlLog(String packageName, String url, boolean isJudi) {
        String deviceId = prefs.getString("device_id", "");
        String appName = UsageStatsMonitor.getAppLabel(this, packageName);

        // Save to local DB
        LogEntry entry = new LogEntry();
        entry.packageName = packageName;
        entry.appName = appName;
        entry.url = url;
        entry.timestamp = System.currentTimeMillis();
        entry.sent = false;
        entry.isJudi = isJudi;

        new Thread(() -> {
            AppDatabase.getInstance(this).logDao().insert(entry);
        }).start();

        // Send immediately to server
        try {
            LogData logData = new LogData(deviceId, packageName, appName, url,
                    System.currentTimeMillis(), isJudi);
            RetrofitClient.getInstance(this).sendLog(logData).enqueue(new Callback<Void>() {
                @Override
                public void onResponse(Call<Void> call, Response<Void> response) {
                    Log.d(TAG, "Log sent OK: " + url + " (status=" + response.code() + ")");
                }

                @Override
                public void onFailure(Call<Void> call, Throwable t) {
                    Log.e(TAG, "Log send FAILED: " + url + " error=" + t.getMessage());
                }
            });
        } catch (Exception e) {
            Log.e(TAG, "Log send exception: " + e.getMessage());
        }
    }

    private void handleJudiDetected(String url) {
        if (!VpnStatus.isVpnActive(this)) {
            lockDevice();
            performGlobalAction(GLOBAL_ACTION_BACK);
        }
    }

    private void lockDevice() {
        try {
            DevicePolicyManager dpm = (DevicePolicyManager) getSystemService(DEVICE_POLICY_SERVICE);
            ComponentName admin = new ComponentName(this, AdminReceiver.class);
            if (dpm != null && dpm.isAdminActive(admin)) {
                dpm.lockNow();
                Log.d(TAG, "🔒 Device LOCKED!");
            } else {
                Log.w(TAG, "Device Admin not active, cannot lock");
            }
        } catch (Exception e) {
            Log.e(TAG, "Lock failed: " + e.getMessage());
        }
    }

    @Override
    public void onInterrupt() {
        notifyAccessibilityDisabled();
    }

    @Override
    public void onDestroy() {
        try {
            unregisterReceiver(quizReceiver);
        } catch (Exception e) {}
        notifyAccessibilityDisabled();
        super.onDestroy();
    }

    private void notifyAccessibilityDisabled() {
        String deviceId = prefs.getString("device_id", "");
        if (deviceId.isEmpty()) return;

        try {
            ServiceAlertRequest request = new ServiceAlertRequest(deviceId, "AccessibilityService");
            RetrofitClient.getInstance().alertServiceDisabled(request)
                    .enqueue(new Callback<Void>() {
                        @Override
                        public void onResponse(Call<Void> call, Response<Void> response) { }

                        @Override
                        public void onFailure(Call<Void> call, Throwable t) { }
                    });
        } catch (Exception e) {
            // Cannot send
        }
    }
}
