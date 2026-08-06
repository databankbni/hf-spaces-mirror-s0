package com.example.parentmonitor;

import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.LinearLayout;

import androidx.appcompat.app.AppCompatActivity;
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout;

import com.google.android.material.button.MaterialButton;

public class MainActivity extends AppCompatActivity {

    private WebView webView;
    private SwipeRefreshLayout swipeRefresh;
    private LinearLayout errorOverlay;
    private String serverUrl;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Check if configured
        SharedPreferences prefs = getSharedPreferences("parent_config", MODE_PRIVATE);
        serverUrl = prefs.getString("server_url", "");
        if (serverUrl.isEmpty()) {
            startActivity(new Intent(this, SetupActivity.class));
            finish();
            return;
        }

        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webView);
        swipeRefresh = findViewById(R.id.swipeRefresh);
        errorOverlay = findViewById(R.id.errorOverlay);
        MaterialButton btnRetry = findViewById(R.id.btnRetry);
        MaterialButton btnChangeServer = findViewById(R.id.btnChangeServer);

        // Configure WebView
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setUseWideViewPort(true);
        settings.setLoadWithOverviewMode(true);

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                swipeRefresh.setRefreshing(false);
                errorOverlay.setVisibility(View.GONE);
                webView.setVisibility(View.VISIBLE);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                super.onReceivedError(view, request, error);
                if (request.isForMainFrame()) {
                    swipeRefresh.setRefreshing(false);
                    errorOverlay.setVisibility(View.VISIBLE);
                    webView.setVisibility(View.GONE);
                }
            }
        });

        webView.setWebChromeClient(new WebChromeClient());

        // Swipe to refresh
        swipeRefresh.setColorSchemeColors(0xFF4ECCA3);
        swipeRefresh.setProgressBackgroundColorSchemeColor(0xFF1A1A2E);
        swipeRefresh.setOnRefreshListener(() -> webView.reload());

        // Error buttons
        btnRetry.setOnClickListener(v -> {
            errorOverlay.setVisibility(View.GONE);
            webView.setVisibility(View.VISIBLE);
            swipeRefresh.setRefreshing(true);
            webView.loadUrl(serverUrl);
        });

        btnChangeServer.setOnClickListener(v -> {
            Intent intent = new Intent(this, SetupActivity.class);
            intent.putExtra("change_server", true);
            startActivity(intent);
            finish();
        });

        // Load dashboard
        webView.loadUrl(serverUrl);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
