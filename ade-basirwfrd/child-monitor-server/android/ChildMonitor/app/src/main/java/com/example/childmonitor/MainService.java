package com.example.childmonitor;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.NetworkRequest;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;

import java.util.concurrent.TimeUnit;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

public class MainService extends Service {
    private static final int NOTIF_ID = 1001;
    private static final String CHANNEL_ID = "monitor_channel";
    public static final String ACTION_AUTO_REGISTER = "com.example.childmonitor.AUTO_REGISTER";
    /** Alarm cepat saat heartbeat/register gagal (OEM membunuh proses / jaringan putus). */
    public static final String ACTION_RECOVERY_PING = "com.example.childmonitor.RECOVERY_PING";
    private static final int REQ_RECOVERY_ALARM = 9997;
    private static final int REQ_WATCHDOG_ALARM = 9999;
    private static final String PREF_LAST_VPN_ALERT = "last_third_party_vpn_alert_ms";
    private static final long VPN_ALERT_COOLDOWN_MS = 6L * 60 * 60 * 1000;
    private static final long[] HEARTBEAT_RETRY_DELAYS_MS = { 4000L, 12000L, 35000L, 60000L };

    private Handler handler;
    private String lastApp = "";
    private SharedPreferences prefs;
    /** Setelah HP mati lama / reboot: begitu jaringan siap, langsung heartbeat + daftar ulang. */
    private ConnectivityManager.NetworkCallback networkResumeCallback;
    private long lastNetworkResumePingMs;
    private BroadcastReceiver userUnlockReceiver;
    private long lastUserUnlockPingMs;

    private final Runnable checkAppTask = new Runnable() {
        @Override
        public void run() {
            // Sync blocklist from server periodically (rate-limited inside)
            JudiFilter.syncBlocklist(MainService.this);

            String currentApp = UsageStatsMonitor.getForegroundApp(MainService.this);
            if (currentApp != null && !currentApp.isEmpty()) {
                if (!currentApp.equals(lastApp)) {
                    // App changed - always log it immediately
                    sendAppLog(currentApp);
                    lastApp = currentApp;

                    if (VpnStatus.isThirdPartyVpnActive(MainService.this)) {
                        notifyVpnActiveMaybe();
                    }
                }
                // Also send periodic heartbeat-like log every 10 seconds
                // so the dashboard always has fresh data
            }
            handler.postDelayed(this, 2000); // Check every 2 seconds
        }
    };

    // Heartbeat task — interval lebih rapat agar dashboard cepat reflect setelah OEM/kill
    private final Runnable heartbeatTask = new Runnable() {
        @Override
        public void run() {
            sendHeartbeat();
            handler.postDelayed(this, 90_000L); // 90 dtk
        }
    };

    // Auto-registration task - every 5 minutes (ensures server has device in DB)
    private final Runnable registrationTask = new Runnable() {
        @Override
        public void run() {
            performAutoRegistration();
            handler.postDelayed(this, 5 * 60 * 1000L); // 5 minutes
        }
    };

    /** Xiaomi/OEM sering mematikan Accessibility — cek & nyalakan ulang. */
    private final Runnable accessibilityGuardTask = new Runnable() {
        @Override
        public void run() {
            AccessibilityGuard.ensureEnabled(MainService.this);
            handler.postDelayed(this, 30_000L);
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        prefs = getSharedPreferences("config", MODE_PRIVATE);
        handler = new Handler(Looper.getMainLooper());

        createNotificationChannel();
        startForegroundNotification();

        // Start monitoring
        handler.post(checkAppTask);
        handler.post(heartbeatTask);
        handler.post(registrationTask);
        handler.post(accessibilityGuardTask);

        // Immediate registration on start
        performAutoRegistration();

        // Device Owner: re-apply uninstall block / restrictions + a11y lock
        if (DeviceOwnerController.isDeviceOwner(this)) {
            DeviceOwnerController.applyCorePolicies(this);
        } else {
            AccessibilityGuard.ensureEnabled(this);
        }

        // Schedule periodic log sender worker
        scheduleLogSender();

        // Schedule AlarmManager watchdog to restart service if killed
        scheduleWatchdog();

        // Schedule WorkManager registration (survives MIUI kills)
        RegistrationWorker.schedule(this);

        registerNetworkResumeListeners();
        registerUserUnlockReceiver();

        // Sinkronkan URL server dengan backend (mencegah salah URL vs Space Hugging Face)
        handler.postDelayed(this::fetchPublicConfigFromServer, 10_000L);
    }

    private void registerUserUnlockReceiver() {
        userUnlockReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                if (!prefs.getBoolean("setup_complete", false)) return;
                long now = SystemClock.elapsedRealtime();
                if (now - lastUserUnlockPingMs < 90_000L) return;
                lastUserUnlockPingMs = now;
                handler.post(() -> {
                    sendHeartbeat();
                    performAutoRegistration();
                });
            }
        };
        IntentFilter filter = new IntentFilter(Intent.ACTION_USER_PRESENT);
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                registerReceiver(userUnlockReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
            } else {
                registerReceiver(userUnlockReceiver, filter);
            }
        } catch (Exception e) {
            Log.w("MainService", "USER_PRESENT receiver: " + e.getMessage());
        }
    }

    /** Heartbeat + register saat jaringan baru tersedia (mis. WiFi menyambung setelah boot). */
    private void onNetworkMaybeReadyForResume() {
        long now = SystemClock.elapsedRealtime();
        if (now - lastNetworkResumePingMs < 10_000L) return;
        lastNetworkResumePingMs = now;
        Log.i("MainService", "Jaringan siap — heartbeat + registrasi");
        sendHeartbeat();
        performAutoRegistration();
    }

    private void registerNetworkResumeListeners() {
        ConnectivityManager cm = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm == null) return;

        networkResumeCallback = new ConnectivityManager.NetworkCallback() {
            @Override
            public void onAvailable(Network network) {
                handler.post(MainService.this::onNetworkMaybeReadyForResume);
            }

            @Override
            public void onCapabilitiesChanged(Network network, NetworkCapabilities caps) {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
                        && caps != null
                        && caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)) {
                    handler.post(MainService.this::onNetworkMaybeReadyForResume);
                }
            }
        };

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N) {
                cm.registerDefaultNetworkCallback(networkResumeCallback);
            } else {
                NetworkRequest req = new NetworkRequest.Builder()
                        .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                        .build();
                cm.registerNetworkCallback(req, networkResumeCallback);
            }
        } catch (Exception e) {
            Log.w("MainService", "registerNetworkCallback: " + e.getMessage());
        }
    }

    private void unregisterNetworkResumeListeners() {
        if (networkResumeCallback == null) return;
        ConnectivityManager cm = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
        try {
            if (cm != null) {
                cm.unregisterNetworkCallback(networkResumeCallback);
            }
        } catch (Exception ignored) {
        }
        networkResumeCallback = null;
    }

    private void createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID,
                    getString(R.string.notification_channel_name),
                    NotificationManager.IMPORTANCE_LOW
            );
            channel.setDescription(getString(R.string.notification_channel_desc));
            channel.setShowBadge(false);

            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                nm.createNotificationChannel(channel);
            }
        }
    }

    private void startForegroundNotification() {
        updateNotification("Aktif - Memantau");
    }

    private void updateNotification(String status) {
        String deviceId = prefs.getString("device_id", "Anak");
        Notification notification = new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("Layanan Sistem (" + deviceId + ")")
                .setContentText("Status: " + status)
                .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
                .setPriority(NotificationCompat.PRIORITY_LOW)
                .setOngoing(true)
                .build();
        startForeground(NOTIF_ID, notification);
    }

    private void sendAppLog(String packageName) {
        String deviceId = prefs.getString("device_id", "");
        String appName = UsageStatsMonitor.getAppLabel(this, packageName);

        // Save to local DB
        LogEntry entry = new LogEntry();
        entry.packageName = packageName;
        entry.appName = appName;
        entry.url = "";
        entry.timestamp = System.currentTimeMillis();
        entry.sent = false;
        entry.isJudi = false;

        new Thread(() -> {
            AppDatabase.getInstance(this).logDao().insert(entry);
        }).start();

        // Also try to send immediately
        try {
            LogData logData = new LogData(deviceId, packageName, appName, "", System.currentTimeMillis(), false);
            RetrofitClient.getInstance(this).sendLog(logData).enqueue(new retrofit2.Callback<Void>() {
                @Override
                public void onResponse(retrofit2.Call<Void> call, retrofit2.Response<Void> response) {
                    // Success
                }

                @Override
                public void onFailure(retrofit2.Call<Void> call, Throwable t) {
                    // Will be retried by LogSenderWorker
                }
            });
        } catch (Exception e) {
            // Network not available, will be sent by worker
        }
    }

    private void sendHeartbeat() {
        sendHeartbeatAttempt(0);
    }

    private void sendHeartbeatAttempt(final int attemptIndex) {
        String deviceId = prefs.getString("device_id", "");
        if (deviceId.isEmpty()) return;

        try {
            RetrofitClient.getInstance(this).heartbeat(HeartbeatRequest.fromContext(this, deviceId))
                    .enqueue(new Callback<Void>() {
                        @Override
                        public void onResponse(Call<Void> call, Response<Void> response) {
                            if (response.isSuccessful()) {
                                cancelRecoveryPing();
                                updateNotification("Aktif - Terhubung");
                            } else {
                                onHeartbeatFailed(attemptIndex, "HTTP " + response.code());
                            }
                        }

                        @Override
                        public void onFailure(Call<Void> call, Throwable t) {
                            onHeartbeatFailed(attemptIndex, t != null ? t.getMessage() : "network");
                        }
                    });
        } catch (Exception e) {
            onHeartbeatFailed(attemptIndex, e.getMessage());
        }
    }

    private void onHeartbeatFailed(int attemptIndex, String reason) {
        Log.w("MainService", "Heartbeat gagal: " + reason + " (percobaan " + attemptIndex + ")");
        if (attemptIndex < HEARTBEAT_RETRY_DELAYS_MS.length) {
            handler.postDelayed(() -> sendHeartbeatAttempt(attemptIndex + 1),
                    HEARTBEAT_RETRY_DELAYS_MS[attemptIndex]);
        } else {
            updateNotification("Menyambung ulang…");
            scheduleRecoveryPing(12_000L);
        }
    }

    /** Alert VPN pihak ketiga — dibatasi supaya tidak spam email. */
    private void notifyVpnActiveMaybe() {
        String deviceId = prefs.getString("device_id", "");
        if (deviceId.isEmpty()) return;

        long now = System.currentTimeMillis();
        long last = prefs.getLong(PREF_LAST_VPN_ALERT, 0L);
        if (now - last < VPN_ALERT_COOLDOWN_MS) return;
        prefs.edit().putLong(PREF_LAST_VPN_ALERT, now).apply();

        try {
            RetrofitClient.getInstance(this).alertVpnDetected(new HeartbeatRequest(deviceId))
                    .enqueue(new Callback<Void>() {
                        @Override
                        public void onResponse(Call<Void> call, Response<Void> response) { }

                        @Override
                        public void onFailure(Call<Void> call, Throwable t) { }
                    });
        } catch (Exception e) {
            // Ignore
        }
    }

    /** Ambil URL kanonik dari server (env PUBLIC_BASE_URL) agar selaras dengan dashboard. */
    private void fetchPublicConfigFromServer() {
        if (!prefs.getBoolean("setup_complete", false)) return;

        new Thread(() -> {
            try {
                Response<PublicConfigResponse> resp = RetrofitClient.getInstance(MainService.this)
                        .getPublicConfig()
                        .execute();
                if (!resp.isSuccessful() || resp.body() == null) return;
                String nu = resp.body().publicBaseUrl;
                if (nu == null || nu.trim().isEmpty()) return;
                nu = nu.trim();
                while (nu.endsWith("/")) {
                    nu = nu.substring(0, nu.length() - 1);
                }
                if (!nu.startsWith("https://")) return;

                String cur = prefs.getString("server_url", "");
                if (cur == null) cur = "";
                while (cur.endsWith("/")) {
                    cur = cur.substring(0, cur.length() - 1);
                }
                if (nu.equals(cur)) return;

                prefs.edit().putString("server_url", nu).apply();
                RetrofitClient.setBaseUrl(nu + "/");
                Log.i("MainService", "URL server diselaraskan dari /api/config: " + nu);
                handler.post(this::performAutoRegistration);
            } catch (Exception e) {
                Log.w("MainService", "fetchPublicConfig: " + e.getMessage());
            }
        }, "public-config").start();
    }

    private void scheduleLogSender() {
        Constraints constraints = new Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build();

        PeriodicWorkRequest workRequest = new PeriodicWorkRequest.Builder(
                LogSenderWorker.class, 15, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .build();

        WorkManager.getInstance(this).enqueueUniquePeriodicWork(
                "log_sender",
                ExistingPeriodicWorkPolicy.KEEP,
                workRequest
        );
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_RECOVERY_PING.equals(intent.getAction())) {
            Log.d("MainService", "Recovery ping (alarm)");
            sendHeartbeat();
            performAutoRegistration();
            return START_STICKY;
        }
        if (intent != null && ACTION_AUTO_REGISTER.equals(intent.getAction())) {
            Log.d("MainService", "Action auto-registration triggered");
            performAutoRegistration();
            sendHeartbeat();
        }
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        try {
            if (userUnlockReceiver != null) {
                unregisterReceiver(userUnlockReceiver);
                userUnlockReceiver = null;
            }
        } catch (Exception ignored) {
        }
        unregisterNetworkResumeListeners();
        handler.removeCallbacks(checkAppTask);
        handler.removeCallbacks(heartbeatTask);
        handler.removeCallbacks(registrationTask);
        handler.removeCallbacks(accessibilityGuardTask);
        // Auto-restart: schedule restart even if destroyed
        scheduleWatchdog();
        super.onDestroy();
    }

    @Override
    public void onTaskRemoved(Intent rootIntent) {
        // User swiped away the app — restart the service immediately
        Log.w("MainService", "⚠️ Task removed! Scheduling restart...");
        scheduleWatchdog();
        super.onTaskRemoved(rootIntent);
    }

    /**
     * Schedule an AlarmManager watchdog that restarts MainService every 5 minutes.
     * This survives Xiaomi MIUI battery kills.
     */
    private void scheduleWatchdog() {
        try {
            Intent intent = new Intent(this, MainService.class);
            intent.setAction(ACTION_AUTO_REGISTER);
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                flags |= PendingIntent.FLAG_IMMUTABLE;
            }
            PendingIntent pi = PendingIntent.getService(this, REQ_WATCHDOG_ALARM, intent, flags);

            AlarmManager am = (AlarmManager) getSystemService(Context.ALARM_SERVICE);
            if (am != null) {
                long triggerAt = SystemClock.elapsedRealtime() + 2 * 60 * 1000L;

                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    am.setAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, triggerAt, pi);
                } else {
                    am.set(AlarmManager.ELAPSED_REALTIME_WAKEUP, triggerAt, pi);
                }
                Log.d("MainService", "Watchdog alarm ~2 min (Doze-aware)");
            }
        } catch (Exception e) {
            Log.e("MainService", "Failed to schedule watchdog: " + e.getMessage());
        }
    }

    /** Alarm sekali untuk menyambung ulang setelah gagal — diganti setiap jadwal baru. */
    private void scheduleRecoveryPing(long delayMs) {
        cancelRecoveryPing();
        try {
            Intent intent = new Intent(this, MainService.class);
            intent.setAction(ACTION_RECOVERY_PING);
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                flags |= PendingIntent.FLAG_IMMUTABLE;
            }
            PendingIntent pi = PendingIntent.getService(this, REQ_RECOVERY_ALARM, intent, flags);
            AlarmManager am = (AlarmManager) getSystemService(Context.ALARM_SERVICE);
            if (am == null) return;
            long at = SystemClock.elapsedRealtime() + Math.max(5000L, delayMs);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                if (am.canScheduleExactAlarms()) {
                    am.setExactAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, at, pi);
                } else {
                    am.setAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, at, pi);
                }
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                am.setAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, at, pi);
            } else {
                am.set(AlarmManager.ELAPSED_REALTIME_WAKEUP, at, pi);
            }
            Log.d("MainService", "Recovery ping scheduled in " + delayMs + "ms");
        } catch (Exception e) {
            Log.w("MainService", "scheduleRecoveryPing: " + e.getMessage());
        }
    }

    private void cancelRecoveryPing() {
        try {
            Intent intent = new Intent(this, MainService.class);
            intent.setAction(ACTION_RECOVERY_PING);
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                flags |= PendingIntent.FLAG_IMMUTABLE;
            }
            PendingIntent pi = PendingIntent.getService(this, REQ_RECOVERY_ALARM, intent, flags);
            AlarmManager am = (AlarmManager) getSystemService(Context.ALARM_SERVICE);
            if (am != null) {
                am.cancel(pi);
            }
            pi.cancel();
        } catch (Exception ignored) {
        }
    }

    private void performAutoRegistration() {
        String deviceId = prefs.getString("device_id", "");
        String waNumber = prefs.getString("wa_number", "ade.basirwfrd@gmail.com");
        String fcmToken = prefs.getString("fcm_token", "");

        if (deviceId.isEmpty()) return;

        Log.d("MainService", "Performing auto-registration for " + deviceId);
        updateNotification("Sedang Mendaftar...");
        RetrofitClient.getInstance(this).register(
                new RegisterRequest(deviceId, waNumber, fcmToken)
        ).enqueue(new Callback<Void>() {
            @Override
            public void onResponse(Call<Void> call, Response<Void> response) {
                if (response.isSuccessful()) {
                    Log.d("MainService", "Auto-registration successful");
                    updateNotification("Aktif - Terhubung");
                } else {
                    Log.e("MainService", "Auto-registration failed: " + response.code());
                    updateNotification("Error: Server mendaftar (" + response.code() + ")");
                }
            }

            @Override
            public void onFailure(Call<Void> call, Throwable t) {
                Log.e("MainService", "Auto-registration error: " + t.getMessage());
                updateNotification("Offline - Menyambung ulang…");
                scheduleRecoveryPing(20_000L);
            }
        });
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
