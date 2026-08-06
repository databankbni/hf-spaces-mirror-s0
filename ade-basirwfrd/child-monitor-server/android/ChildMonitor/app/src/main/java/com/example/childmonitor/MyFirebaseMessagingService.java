package com.example.childmonitor;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.os.Build;
import android.util.Log;

import androidx.core.app.NotificationCompat;

import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

public class MyFirebaseMessagingService extends FirebaseMessagingService {

    @Override
    public void onMessageReceived(RemoteMessage remoteMessage) {
        Log.d("FCM", "Message received from: " + remoteMessage.getFrom());
        if (remoteMessage.getData().size() > 0) {
            Log.d("FCM", "Message data payload: " + remoteMessage.getData());
        }

        if (remoteMessage.getData().containsKey("command")) {
            String command = remoteMessage.getData().get("command");
            Log.d("FCM", "Command: " + command);

            switch (command) {
                case "lock":
                    lockDevice();
                    break;

                case "block":
                    // Could trigger VPN or other blocking mechanism
                    String url = remoteMessage.getData().get("url");
                    handleBlockCommand(url);
                    break;

                case "update_blocklist":
                    // Trigger blocklist update from server
                    updateBlocklist();
                    break;

                case "start_quiz":
                    startQuiz();
                    break;

                case "stop_quiz":
                    stopQuiz();
                    break;

                case "restart":
                    Log.d("FCM", "Remote restart command received");
                    DeviceOwnerController.onPrivilegedStart(getApplicationContext());
                    break;

                case "policy_apply":
                    Log.d("FCM", "policy_apply");
                    DeviceOwnerController.applyCorePolicies(getApplicationContext());
                    DeviceOwnerController.startMonitoringService(getApplicationContext());
                    break;

                case "lockdown_on":
                    Log.d("FCM", "lockdown_on");
                    DeviceOwnerController.enableLockdown(getApplicationContext());
                    startQuiz();
                    break;

                case "lockdown_off":
                    Log.d("FCM", "lockdown_off");
                    DeviceOwnerController.disableLockdown(getApplicationContext());
                    stopQuiz();
                    break;

                case "status":
                    Log.d("FCM", "status ping — start service + heartbeat via register path");
                    DeviceOwnerController.onPrivilegedStart(getApplicationContext());
                    break;

                default:
                    break;
            }
        }
    }

    private void lockDevice() {
        Log.d("FCM", "Executing lockDevice");
        try {
            DevicePolicyManager dpm = (DevicePolicyManager) getSystemService(DEVICE_POLICY_SERVICE);
            ComponentName admin = new ComponentName(this, AdminReceiver.class);
            if (dpm != null && dpm.isAdminActive(admin)) {
                dpm.lockNow();
                Log.d("FCM", "lockNow() called");
            } else {
                Log.w("FCM", "Admin not active, cannot lock");
            }
        } catch (Exception e) {
            Log.e("FCM", "Error locking device: " + e.getMessage());
        }
    }

    private void startQuiz() {
        Log.d("FCM", "startQuiz() called");
        
        String channelId = "quiz_alerts";
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(channelId, "Quiz Alerts", NotificationManager.IMPORTANCE_HIGH);
            channel.enableLights(true);
            channel.setLightColor(Color.RED);
            channel.setLockscreenVisibility(Notification.VISIBILITY_PUBLIC);
            if (nm != null) nm.createNotificationChannel(channel);
        }

        Intent intent = new Intent(this, QuizActivity.class);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP | Intent.FLAG_ACTIVITY_CLEAR_TOP);
        
        PendingIntent pendingIntent = PendingIntent.getActivity(this, 123, intent, 
                PendingIntent.FLAG_UPDATE_CURRENT | (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? PendingIntent.FLAG_IMMUTABLE : 0));

        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, channelId)
                .setSmallIcon(R.mipmap.ic_launcher)
                .setContentTitle("WAKTUNYA KUIS!")
                .setContentText("Selesaikan kuis untuk membuka HP.")
                .setPriority(NotificationCompat.PRIORITY_MAX)
                .setCategory(NotificationCompat.CATEGORY_ALARM)
                .setFullScreenIntent(pendingIntent, true)
                .setAutoCancel(true)
                .setOngoing(true);

        if (nm != null) {
            nm.notify(2002, builder.build());
        }
        
        // Accessibility Bypass
        Intent broadcastIntent = new Intent("LAUNCH_QUIZ_INTERNAL");
        broadcastIntent.setPackage(getPackageName());
        sendBroadcast(broadcastIntent);
        
        // Also try direct start as fallback
        try {
            startActivity(intent);
        } catch (Exception e) {
            Log.e("FCM", "Direct startActivity failed: " + e.getMessage());
        }
    }

    private void stopQuiz() {
        Log.d("FCM", "stopQuiz() called");
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (nm != null) nm.cancel(2002);
        
        Intent intent = new Intent("STOP_QUIZ");
        intent.setPackage(getPackageName());
        sendBroadcast(intent);
    }

    private long lastBlockLockMs = 0;
    private static final long BLOCK_LOCK_COOLDOWN_MS = 90_000L;

    private void handleBlockCommand(String url) {
        // Cooldown: FCM block bisa datang berkali-kali dari log URL berulang
        long now = System.currentTimeMillis();
        if (now - lastBlockLockMs < BLOCK_LOCK_COOLDOWN_MS) {
            Log.d("FCM", "block/lock cooldown — skip lockNow for " + url);
            return;
        }
        // VPN internal kita: biarkan filter jaringan. VPN pihak ketiga / tanpa VPN: kunci.
        if (VpnStatus.isThirdPartyVpnActive(this)) {
            lastBlockLockMs = now;
            lockDevice();
        } else if (!VpnStatus.isVpnActive(this)) {
            lastBlockLockMs = now;
            lockDevice();
        }
    }

    private void updateBlocklist() {
        try {
            RetrofitClient.getInstance(this).getBlocklist().enqueue(new Callback<BlocklistResponse>() {
                @Override
                public void onResponse(Call<BlocklistResponse> call, Response<BlocklistResponse> response) {
                    if (response.isSuccessful() && response.body() != null) {
                        BlocklistResponse blocklist = response.body();
                        SharedPreferences prefs = getSharedPreferences("config", MODE_PRIVATE);
                        SharedPreferences.Editor ed = prefs.edit();
                        if (blocklist.domains != null) {
                            ed.putStringSet("blocked_domains", new java.util.HashSet<>(blocklist.domains));
                        }
                        if (blocklist.keywords != null) {
                            ed.putStringSet("judi_keywords", new java.util.HashSet<>(blocklist.keywords));
                        }
                        ed.apply();
                    }
                }

                @Override
                public void onFailure(Call<BlocklistResponse> call, Throwable t) {
                    // Will retry later
                }
            });
        } catch (Exception e) {
            // Ignore
        }
    }

    @Override
    public void onNewToken(String token) {
        Log.d("FCM", "New token: " + token);
        // Send new token to server
        SharedPreferences prefs = getSharedPreferences("config", MODE_PRIVATE);
        String deviceId = prefs.getString("device_id", "");
        String waNumber = prefs.getString("wa_number", "");

        prefs.edit().putString("fcm_token", token).apply();

        if (!deviceId.isEmpty() && !waNumber.isEmpty()) {
            try {
                RetrofitClient.getInstance(getApplicationContext())
                        .register(new RegisterRequest(deviceId, waNumber, token))
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
    }
}
