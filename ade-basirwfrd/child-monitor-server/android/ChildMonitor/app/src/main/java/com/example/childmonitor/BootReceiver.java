package com.example.childmonitor;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;

import androidx.work.Constraints;
import androidx.work.ExistingWorkPolicy;
import androidx.work.NetworkType;
import androidx.work.OneTimeWorkRequest;
import androidx.work.WorkManager;

import java.util.concurrent.TimeUnit;

/**
 * Receiver that starts the monitoring service after:
 * - Device boot / quick boot
 * - App update (MY_PACKAGE_REPLACED)
 * Device Owner: start even if setup UI never reopened (policies + FGS).
 */
public class BootReceiver extends BroadcastReceiver {

    private static final String BOOT_RESUME_WORK = "boot_resume_registration";

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent != null ? intent.getAction() : null;
        if (action == null) return;

        boolean bootLike =
                Intent.ACTION_BOOT_COMPLETED.equals(action)
                || Intent.ACTION_MY_PACKAGE_REPLACED.equals(action)
                || "android.intent.action.QUICKBOOT_POWERON".equals(action)
                || "com.htc.intent.action.QUICKBOOT_POWERON".equals(action);

        if (!bootLike) return;

        Log.d("BootReceiver", "Received: " + action);
        SharedPreferences prefs = context.getSharedPreferences("config", Context.MODE_PRIVATE);
        boolean setupComplete = prefs.getBoolean("setup_complete", false);
        boolean deviceOwner = DeviceOwnerController.isDeviceOwner(context);

        if (!setupComplete && !deviceOwner) {
            Log.d("BootReceiver", "Setup incomplete and not DO — skip");
            return;
        }

        DeviceOwnerController.onPrivilegedStart(context.getApplicationContext());

        Constraints net = new Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build();
        OneTimeWorkRequest once = new OneTimeWorkRequest.Builder(RegistrationWorker.class)
                .setConstraints(net)
                .setInitialDelay(5, TimeUnit.SECONDS)
                .build();
        WorkManager.getInstance(context.getApplicationContext())
                .enqueueUniqueWork(BOOT_RESUME_WORK, ExistingWorkPolicy.REPLACE, once);
    }
}
