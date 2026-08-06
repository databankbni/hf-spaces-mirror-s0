package com.example.parentmonitor;

import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.View;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;

import com.google.android.material.button.MaterialButton;
import com.google.android.material.textfield.TextInputEditText;

import java.net.HttpURLConnection;
import java.net.URL;

public class SetupActivity extends AppCompatActivity {

    private TextInputEditText etServerUrl;
    private MaterialButton btnConnect;
    private TextView tvStatus;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Default server URL — change this to your server's IP
        // Ganti ke URL always-on (Fly/Railway) setelah migrate — HF sering sleep
        final String DEFAULT_SERVER_URL = "https://ade-basirwfrd-child-monitor-server.hf.space";

        SharedPreferences prefs = getSharedPreferences("parent_config", MODE_PRIVATE);
        String savedUrl = prefs.getString("server_url", "");

        // Auto-save default URL on first launch and skip setup
        if (savedUrl.isEmpty()) {
            prefs.edit().putString("server_url", DEFAULT_SERVER_URL).apply();
            savedUrl = DEFAULT_SERVER_URL;
        }

        // If already configured and not changing server, go to main
        if (!getIntent().getBooleanExtra("change_server", false)) {
            startActivity(new Intent(this, MainActivity.class));
            finish();
            return;
        }

        setContentView(R.layout.activity_setup);

        etServerUrl = findViewById(R.id.etServerUrl);
        btnConnect = findViewById(R.id.btnConnect);
        tvStatus = findViewById(R.id.tvStatus);

        // Pre-fill if exists
        if (!savedUrl.isEmpty()) {
            etServerUrl.setText(savedUrl);
        }

        btnConnect.setOnClickListener(v -> {
            String url = etServerUrl.getText().toString().trim();
            if (url.isEmpty()) {
                tvStatus.setVisibility(View.VISIBLE);
                tvStatus.setText("URL server tidak boleh kosong");
                return;
            }

            // Remove trailing slash
            if (url.endsWith("/")) url = url.substring(0, url.length() - 1);

            btnConnect.setEnabled(false);
            btnConnect.setText("Menghubungkan...");
            tvStatus.setVisibility(View.GONE);

            // Test connection in background
            String finalUrl = url;
            new Thread(() -> {
                boolean connected = testConnection(finalUrl);
                runOnUiThread(() -> {
                    btnConnect.setEnabled(true);
                    btnConnect.setText(getString(R.string.btn_connect));

                    if (connected) {
                        // Save and go to main
                        prefs.edit().putString("server_url", finalUrl).apply();
                        Toast.makeText(this, "✅ Terhubung ke server!", Toast.LENGTH_SHORT).show();
                        startActivity(new Intent(this, MainActivity.class));
                        finish();
                    } else {
                        tvStatus.setVisibility(View.VISIBLE);
                        tvStatus.setText("❌ Tidak bisa terhubung ke server.\nPastikan URL benar dan server berjalan.");
                    }
                });
            }).start();
        });
    }

    private boolean testConnection(String serverUrl) {
        try {
            URL url = new URL(serverUrl + "/api/health");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(5000);
            conn.setReadTimeout(5000);
            int code = conn.getResponseCode();
            conn.disconnect();
            return code == 200;
        } catch (Exception e) {
            return false;
        }
    }
}
