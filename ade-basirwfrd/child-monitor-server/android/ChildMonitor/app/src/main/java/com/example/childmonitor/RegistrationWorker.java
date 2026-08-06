package com.example.childmonitor;

import android.content.Context;
import android.content.SharedPreferences;
import android.os.Build;
import android.content.Intent;
import android.util.Log;

import androidx.annotation.NonNull;
import androidx.work.Constraints;
import androidx.work.ExistingPeriodicWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.PeriodicWorkRequest;
import androidx.work.WorkManager;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

/**
 * WorkManager-based periodic registration worker.
 * 
 * This is the ULTIMATE safety net:
 * - Survives process kills by MIUI/Android
 * - Survives app force-stop
 * - Runs every 15 minutes regardless of MainService status
 * - Also restarts MainService if it's not running
 */
public class RegistrationWorker extends Worker {

    private static final String TAG = "RegistrationWorker";
    public static final String WORK_NAME = "auto_registration";

    public RegistrationWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    @NonNull
    @Override
    public Result doWork() {
        Log.d(TAG, "🔄 Periodic registration running...");

        Context ctx = getApplicationContext();
        SharedPreferences prefs = ctx.getSharedPreferences("config", Context.MODE_PRIVATE);
        boolean setupComplete = prefs.getBoolean("setup_complete", false);

        if (!setupComplete) {
            Log.d(TAG, "Setup not complete, skipping");
            return Result.success();
        }

        String deviceId = prefs.getString("device_id", "");
        String waNumber = prefs.getString("wa_number", "");
        String fcmToken = prefs.getString("fcm_token", "");

        if (deviceId.isEmpty()) {
            Log.d(TAG, "No device ID, skipping");
            return Result.success();
        }

        // 1. Register with server (ensures device is in DB even after server restart)
        CountDownLatch latch = new CountDownLatch(1);
        AtomicBoolean success = new AtomicBoolean(false);

        try {
            RetrofitClient.getInstance(ctx).register(
                new RegisterRequest(deviceId, waNumber, fcmToken)
            ).enqueue(new Callback<Void>() {
                @Override
                public void onResponse(Call<Void> call, Response<Void> response) {
                    Log.d(TAG, "✅ Registration OK: " + response.code());
                    success.set(true);
                    latch.countDown();
                }

                @Override
                public void onFailure(Call<Void> call, Throwable t) {
                    Log.e(TAG, "❌ Registration failed: " + t.getMessage());
                    latch.countDown();
                }
            });

            latch.await(30, TimeUnit.SECONDS);
        } catch (Exception e) {
            Log.e(TAG, "Registration error: " + e.getMessage());
        }

        // 2. Heartbeat sinkron (WorkManager — jaringan sudah CONNECTED)
        CountDownLatch hbLatch = new CountDownLatch(1);
        try {
            RetrofitClient.getInstance(ctx).heartbeat(HeartbeatRequest.fromContext(ctx, deviceId))
                .enqueue(new Callback<Void>() {
                    @Override
                    public void onResponse(Call<Void> call, Response<Void> response) {
                        Log.d(TAG, "💓 Heartbeat OK: " + response.code());
                        hbLatch.countDown();
                    }

                    @Override
                    public void onFailure(Call<Void> call, Throwable t) {
                        Log.e(TAG, "💓 Heartbeat fail: " + (t != null ? t.getMessage() : ""));
                        hbLatch.countDown();
                    }
                });
            hbLatch.await(20, TimeUnit.SECONDS);
        } catch (Exception e) {
            Log.e(TAG, "Heartbeat: " + e.getMessage());
        }

        // 2b. Accessibility (Xiaomi sering mematikan)
        try {
            AccessibilityGuard.ensureEnabled(ctx);
        } catch (Exception e) {
            Log.w(TAG, "AccessibilityGuard: " + e.getMessage());
        }

        // 3. Restart MainService if not running
        try {
            Intent serviceIntent = new Intent(ctx, MainService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                ctx.startForegroundService(serviceIntent);
            } else {
                ctx.startService(serviceIntent);
            }
            Log.d(TAG, "🔁 MainService restart triggered");
        } catch (Exception e) {
            Log.e(TAG, "Failed to restart MainService: " + e.getMessage());
        }

        return Result.success();
    }

    /**
     * Schedule periodic registration. Call this once during setup or boot.
     * WorkManager guarantees execution even if MIUI kills the app.
     */
    public static void schedule(Context context) {
        Constraints constraints = new Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build();

        PeriodicWorkRequest workRequest = new PeriodicWorkRequest.Builder(
            RegistrationWorker.class, 15, TimeUnit.MINUTES)
            .setConstraints(constraints)
            .build();

        WorkManager.getInstance(context).enqueueUniquePeriodicWork(
            WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            workRequest
        );

        Log.d(TAG, "⏰ Periodic registration scheduled (every 15 min)");
    }
}
