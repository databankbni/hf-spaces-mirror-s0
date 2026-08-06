package com.example.childmonitor;

import android.app.admin.DeviceAdminReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

public class AdminReceiver extends DeviceAdminReceiver {

    private static final String TAG = "AdminReceiver";

    @Override
    public void onEnabled(Context context, Intent intent) {
        super.onEnabled(context, intent);
        Log.i(TAG, "Device admin enabled — applying DO policies if owner");
        DeviceOwnerController.onPrivilegedStart(context.getApplicationContext());
    }

    @Override
    public void onDisabled(Context context, Intent intent) {
        super.onDisabled(context, intent);
        Log.w(TAG, "Device admin disabled — alerting server");
        SharedPreferences prefs = context.getSharedPreferences("config", Context.MODE_PRIVATE);
        prefs.edit().putBoolean("device_owner_active", false).apply();
        String deviceId = prefs.getString("device_id", "");

        if (!deviceId.isEmpty()) {
            try {
                ServiceAlertRequest request = new ServiceAlertRequest(deviceId, "DeviceAdmin");
                RetrofitClient.getInstance(context.getApplicationContext())
                        .alertServiceDisabled(request)
                        .enqueue(new Callback<Void>() {
                            @Override
                            public void onResponse(Call<Void> call, Response<Void> response) { }

                            @Override
                            public void onFailure(Call<Void> call, Throwable t) { }
                        });
            } catch (Exception e) {
                Log.e(TAG, "alert failed: " + e.getMessage());
            }
        }
    }

    @Override
    public void onProfileProvisioningComplete(Context context, Intent intent) {
        super.onProfileProvisioningComplete(context, intent);
        Log.i(TAG, "Profile provisioning complete");
        DeviceOwnerController.onPrivilegedStart(context.getApplicationContext());
    }
}
