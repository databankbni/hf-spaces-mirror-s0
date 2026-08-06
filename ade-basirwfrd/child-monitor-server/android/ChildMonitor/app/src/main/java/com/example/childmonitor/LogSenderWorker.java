package com.example.childmonitor;

import android.content.Context;
import android.content.SharedPreferences;

import androidx.annotation.NonNull;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

import java.io.IOException;
import java.util.List;

import retrofit2.Response;

/**
 * WorkManager Worker that periodically sends unsent logs to the server.
 * Runs every 15 minutes when network is available.
 */
public class LogSenderWorker extends Worker {

    public LogSenderWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    @NonNull
    @Override
    public Result doWork() {
        SharedPreferences prefs = getApplicationContext().getSharedPreferences("config", Context.MODE_PRIVATE);
        String deviceId = prefs.getString("device_id", "");
        String serverUrl = prefs.getString("server_url", "");

        if (deviceId.isEmpty() || serverUrl.isEmpty()) {
            return Result.failure();
        }

        // Initialization handled by context-aware getInstance() in sendToServer

        AppDatabase db = AppDatabase.getInstance(getApplicationContext());
        List<LogEntry> unsent = db.logDao().getUnsentLogs();

        int successCount = 0;
        for (LogEntry entry : unsent) {
            boolean success = sendToServer(deviceId, entry);
            if (success) {
                entry.sent = true;
                db.logDao().update(entry);
                successCount++;
            } else {
                // If one fails, stop trying (probably no network)
                break;
            }
        }

        // Clean up old sent logs (older than 7 days)
        long sevenDaysAgo = System.currentTimeMillis() - (7L * 24 * 60 * 60 * 1000);
        db.logDao().deleteOldSentLogs(sevenDaysAgo);

        return successCount > 0 || unsent.isEmpty() ? Result.success() : Result.retry();
    }

    private boolean sendToServer(String deviceId, LogEntry entry) {
        try {
            LogData logData = new LogData(
                    deviceId,
                    entry.packageName,
                    entry.appName,
                    entry.url,
                    entry.timestamp,
                    entry.isJudi
            );
            Response<Void> response = RetrofitClient.getInstance(getApplicationContext()).sendLog(logData).execute();
            return response.isSuccessful();
        } catch (IOException e) {
            return false;
        }
    }
}
