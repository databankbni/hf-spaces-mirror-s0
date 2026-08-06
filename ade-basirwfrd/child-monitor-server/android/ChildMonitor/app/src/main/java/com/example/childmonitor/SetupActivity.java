package com.example.childmonitor;

import android.Manifest;
import android.app.admin.DevicePolicyManager;
import android.content.ComponentName;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Toast;
import android.util.Log;
import androidx.appcompat.app.AppCompatActivity;

import com.google.firebase.messaging.FirebaseMessaging;

import java.util.UUID;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

public class SetupActivity extends AppCompatActivity {
    private EditText etWaNumber;
    private EditText etServerUrl;
    private EditText etDeviceName;
    private Button btnSave;
    private TextView tvStatus;
    private TextView tvAdminStatus;
    private SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_setup);

        prefs = getSharedPreferences("config", MODE_PRIVATE);
        etWaNumber = findViewById(R.id.et_wa_number);
        etServerUrl = findViewById(R.id.et_server_url);
        etDeviceName = findViewById(R.id.et_device_name);
        btnSave = findViewById(R.id.btn_save);
        tvStatus = findViewById(R.id.tv_status);
        tvAdminStatus = findViewById(R.id.tv_admin_status);

        String defaultUrl = BuildConfig.DEFAULT_SERVER_URL;
        if (defaultUrl.endsWith("/")) {
            defaultUrl = defaultUrl.substring(0, defaultUrl.length() - 1);
        }
        etWaNumber.setText(prefs.getString("wa_number", "ade.basirwfrd@gmail.com"));
        etServerUrl.setText(prefs.getString("server_url", defaultUrl));
        etDeviceName.setText(prefs.getString("device_id", "anak1"));

        String adminLabel = DeviceOwnerController.statusLabel(this);
        tvAdminStatus.setText("Status admin: " + adminLabel
                + (DeviceOwnerController.isDeviceOwner(this)
                ? " — kebijakan anti-uninstall aktif"
                : " — jalankan enroll-device-owner.sh untuk Device Owner"));

        if (Build.VERSION.SDK_INT >= 33) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{ Manifest.permission.POST_NOTIFICATIONS }, 2001);
            }
        }

        btnSave.setOnClickListener(v -> setupMonitoring());

        if (DeviceOwnerController.isDeviceOwner(this)) {
            DeviceOwnerController.applyCorePolicies(this);
        }
    }

    private void setupMonitoring() {
        String waNumber = etWaNumber.getText().toString().trim();
        String serverUrl = etServerUrl.getText().toString().trim();
        String deviceName = etDeviceName.getText().toString().trim();

        if (waNumber.isEmpty()) {
            etWaNumber.setError("Nomor WA wajib diisi");
            return;
        }
        if (serverUrl.isEmpty()) {
            etServerUrl.setError("URL server wajib diisi");
            return;
        }
        if (deviceName.isEmpty()) {
            deviceName = UUID.randomUUID().toString().substring(0, 8);
        }
        // Satu HP = satu device_id kanonik (hindari duplikat Irfan/irfan)
        deviceName = deviceName.trim().replaceAll("\\s+", "_");

        // Ensure server URL ends without trailing slash
        if (serverUrl.endsWith("/")) {
            serverUrl = serverUrl.substring(0, serverUrl.length() - 1);
        }

        // Save config
        String deviceId = deviceName;
        prefs.edit()
                .putString("wa_number", waNumber)
                .putString("server_url", serverUrl)
                .putString("device_id", deviceId)
                .putBoolean("setup_complete", true)
                .apply();

        // Update Retrofit base URL
        RetrofitClient.setBaseUrl(serverUrl + "/");

        tvStatus.setText("Mengaktifkan izin...");

        // Step 1: Request Usage Stats permission
        try {
            startActivity(new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS));
        } catch (Exception e) {
            tvStatus.setText("Gagal membuka pengaturan Usage Stats");
        }

        // Step 2: Request Accessibility Service
        try {
            startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
        } catch (Exception e) {
            tvStatus.setText("Gagal membuka pengaturan Aksesibilitas");
        }

        // Step 3: Request Device Admin
        ComponentName admin = new ComponentName(this, AdminReceiver.class);
        Intent intentAdmin = new Intent(DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN);
        intentAdmin.putExtra(DevicePolicyManager.EXTRA_DEVICE_ADMIN, admin);
        intentAdmin.putExtra(DevicePolicyManager.EXTRA_ADD_EXPLANATION,
                "Digunakan untuk mengunci layar dari jarak jauh");
        startActivityForResult(intentAdmin, 100);

        // Step 4: Request ignore battery optimization
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
            if (pm != null && !pm.isIgnoringBatteryOptimizations(getPackageName())) {
                Log.d("Setup", "Requesting battery optimization exemption...");
                Intent intentBattery = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
                intentBattery.setData(Uri.parse("package:" + getPackageName()));
                startActivity(intentBattery);
                Toast.makeText(this, "PENTING: Pilih 'Jangan Batasi' (No Restrictions) untuk aplikasi ini!", Toast.LENGTH_LONG).show();
            } else {
                Log.d("Setup", "Battery optimization already ignored.");
            }
        }

        // Step 4b: Baterai / autostart per OEM (Samsung, Xiaomi, OPPO, Vivo, Huawei, dll.)
        OemPowerSetupHelper.openManufacturerPowerSettings(this);
        Toast.makeText(this,
                "Jika muncul beberapa layar pengaturan: izinkan autostart & tanpa batas baterai untuk aplikasi ini.",
                Toast.LENGTH_LONG).show();

        // Step 5: Get FCM token and register to server
        String finalDeviceId = deviceId;
        String finalWaNumber = waNumber;
        FirebaseMessaging.getInstance().getToken()
                .addOnCompleteListener(task -> {
                    if (task.isSuccessful()) {
                        String token = task.getResult();
                        prefs.edit().putString("fcm_token", token).apply();
                        registerToServer(finalDeviceId, finalWaNumber, token);
                    } else {
                        tvStatus.setText("Gagal mendapatkan FCM token. Coba lagi nanti.");
                        // Still register without token
                        registerToServer(finalDeviceId, finalWaNumber, "");
                    }
                });

        // Step 6: Start foreground service (+ DO policies)
        DeviceOwnerController.onPrivilegedStart(getApplicationContext());

        Toast.makeText(this, "Pengaturan selesai. Aplikasi akan berjalan di background.",
                Toast.LENGTH_LONG).show();

        // Close activity after a short delay
        tvStatus.postDelayed(this::finish, 3000);
    }

    private void registerToServer(String deviceId, String waNumber, String fcmToken) {
        try {
            RetrofitClient.getInstance(SetupActivity.this).register(
                    new RegisterRequest(deviceId, waNumber, fcmToken)
            ).enqueue(new Callback<Void>() {
                @Override
                public void onResponse(Call<Void> call, Response<Void> response) {
                    if (response.isSuccessful()) {
                        tvStatus.setText("✓ Terdaftar di server");
                    } else {
                        tvStatus.setText("Gagal mendaftar: " + response.code());
                    }
                }

                @Override
                public void onFailure(Call<Void> call, Throwable t) {
                    tvStatus.setText("Gagal koneksi ke server: " + t.getMessage());
                }
            });
        } catch (Exception e) {
            tvStatus.setText("Error: " + e.getMessage());
        }
    }
}
