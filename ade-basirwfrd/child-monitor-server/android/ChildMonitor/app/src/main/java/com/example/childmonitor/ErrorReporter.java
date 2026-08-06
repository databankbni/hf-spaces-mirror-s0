package com.example.childmonitor;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

import java.io.PrintWriter;
import java.io.StringWriter;

/**
 * Utility to send error reports to the backend server
 * for remote debugging by parents
 */
public class ErrorReporter {

    private static final String TAG = "ErrorReporter";

    /**
     * Report an error to the backend
     * @param context Application context
     * @param errorType Type of error (e.g., "CRASH", "NETWORK", "PERMISSION", "SERVICE")
     * @param errorMessage Human-readable error message
     * @param throwable Optional exception with stack trace
     * @param component Component where error occurred (e.g., "MainService", "URLMonitoringService")
     */
    public static void report(Context context, String errorType, String errorMessage,
                               Throwable throwable, String component) {
        try {
            SharedPreferences prefs = context.getSharedPreferences("config", Context.MODE_PRIVATE);
            String deviceId = prefs.getString("device_id", "");
            String serverUrl = prefs.getString("server_url", "");

            if (deviceId.isEmpty() || serverUrl.isEmpty()) {
                Log.w(TAG, "Cannot report error - not configured yet");
                return;
            }

            if (!serverUrl.endsWith("/")) serverUrl += "/";
            RetrofitClient.setBaseUrl(serverUrl);

            String stackTrace = "";
            if (throwable != null) {
                StringWriter sw = new StringWriter();
                throwable.printStackTrace(new PrintWriter(sw));
                stackTrace = sw.toString();
                // Limit stack trace length
                if (stackTrace.length() > 2000) {
                    stackTrace = stackTrace.substring(0, 2000) + "\n... (truncated)";
                }
            }

            ErrorLogRequest request = new ErrorLogRequest(
                    deviceId, errorType, errorMessage, stackTrace, component);

            RetrofitClient.getInstance().sendErrorLog(request)
                    .enqueue(new Callback<Void>() {
                        @Override
                        public void onResponse(Call<Void> call, Response<Void> response) {
                            Log.d(TAG, "Error report sent: " + errorType);
                        }

                        @Override
                        public void onFailure(Call<Void> call, Throwable t) {
                            Log.w(TAG, "Failed to send error report: " + t.getMessage());
                        }
                    });
        } catch (Exception e) {
            Log.e(TAG, "Error in ErrorReporter itself: " + e.getMessage());
        }
    }

    /**
     * Set up global uncaught exception handler
     */
    public static void setupGlobalHandler(Context context) {
        Thread.UncaughtExceptionHandler defaultHandler = Thread.getDefaultUncaughtExceptionHandler();

        Thread.setDefaultUncaughtExceptionHandler((thread, throwable) -> {
            report(context, "CRASH", throwable.getMessage(), throwable, "UncaughtException");

            // Give time for the report to be sent
            try { Thread.sleep(1000); } catch (InterruptedException ignored) { }

            // Call default handler
            if (defaultHandler != null) {
                defaultHandler.uncaughtException(thread, throwable);
            }
        });
    }
}
