package com.example.childmonitor;

import android.content.Intent;
import android.os.Build;
import okhttp3.OkHttpClient;
import okhttp3.logging.HttpLoggingInterceptor;
import retrofit2.Retrofit;
import retrofit2.converter.gson.GsonConverterFactory;

import java.util.concurrent.TimeUnit;

/**
 * Base URL diambil dari SharedPreferences "config"/"server_url" hanya jika {@link #getInstance(android.content.Context)}
 * dipanggil dengan Context (bukan null). Layanan latar seperti {@link com.google.firebase.messaging.FirebaseMessagingService}
 * harus memanggil {@code getInstance(getApplicationContext())} agar URL server custom tetap dipakai.
 */
public class RetrofitClient {
    private static final String DEFAULT_URL = BuildConfig.DEFAULT_SERVER_URL;
    private static String BASE_URL = DEFAULT_URL;
    private static ApiService apiService;
    private static Retrofit retrofit;

    private static android.content.Context mAppContext;

    public static void setBaseUrl(String url) {
        BASE_URL = url;
        // Reset to force rebuild with new URL
        apiService = null;
        retrofit = null;
    }

    public static ApiService getInstance(android.content.Context context) {
        if (context != null && mAppContext == null) {
            mAppContext = context.getApplicationContext();
        }

        // If apiService is null, always rebuild.
        // If mAppContext is now available and the service was built without a context (or with a transient one), rebuild.
        // We can infer "built without a context" if BASE_URL is still DEFAULT_URL but mAppContext is now set,
        // implying we might have a saved URL to load.
        if (apiService == null || (mAppContext != null && BASE_URL.equals(DEFAULT_URL) && !retrofit.baseUrl().toString().equals(DEFAULT_URL))) {
            // The condition `!retrofit.baseUrl().toString().equals(DEFAULT_URL)` is a bit of a hack
            // to detect if BASE_URL was updated by setBaseUrl but retrofit wasn't rebuilt yet.
            // A simpler approach is to always rebuild if mAppContext is now available and the service
            // was previously built without a persistent context.
            // Let's simplify: if mAppContext is now available and the current service might not have used it, rebuild.
            // This is a heuristic. The most robust way is to always rebuild if mAppContext changes from null to non-null.
            if (apiService == null || (mAppContext != null && (retrofit == null || !retrofit.baseUrl().toString().equals(BASE_URL)))) {
                rebuildService(mAppContext != null ? mAppContext : context);
            }
        }
        return apiService;
    }

    private static void rebuildService(android.content.Context context) {
        if (context != null) {
            mAppContext = context.getApplicationContext();
            // Load from preferences if context is provided
            android.content.SharedPreferences prefs = context.getSharedPreferences("config", android.content.Context.MODE_PRIVATE);
            String savedUrl = prefs.getString("server_url", DEFAULT_URL);
            if (savedUrl.isEmpty()) savedUrl = DEFAULT_URL;
            if (!savedUrl.endsWith("/")) savedUrl += "/";
            BASE_URL = savedUrl;
        } else if (BASE_URL.equals(DEFAULT_URL)) { // If no context and BASE_URL is still default, ensure it's default
            BASE_URL = DEFAULT_URL;
        }

        HttpLoggingInterceptor logging = new HttpLoggingInterceptor();
        logging.setLevel(HttpLoggingInterceptor.Level.BODY);

        OkHttpClient client = new OkHttpClient.Builder()
                .connectTimeout(30, TimeUnit.SECONDS)
                .readTimeout(30, TimeUnit.SECONDS)
                .writeTimeout(30, TimeUnit.SECONDS)
                .addInterceptor(logging)
                .addInterceptor(chain -> {
                    okhttp3.Request request = chain.request();
                    okhttp3.Response response = chain.proceed(request);

                    if (response.code() == 401) {
                        // Self-healing: Trigger re-registration if device is unknown to server
                        android.util.Log.w("RetrofitClient", "Server returned 401. Triggering self-healing registration.");
                        android.content.Context targetContext = mAppContext != null ? mAppContext : context;
                        if (targetContext != null) {
                            Intent regIntent = new Intent(targetContext, MainService.class);
                            regIntent.setAction(MainService.ACTION_AUTO_REGISTER);
                            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                                targetContext.startForegroundService(regIntent);
                            } else {
                                targetContext.startService(regIntent);
                            }
                        }
                    }
                    return response;
                })
                .build();

        retrofit = new Retrofit.Builder()
                .baseUrl(BASE_URL)
                .client(client)
                .addConverterFactory(GsonConverterFactory.create())
                .build();

        apiService = retrofit.create(ApiService.class);
    }

    public static ApiService getInstance() {
        return getInstance(null);
    }
}
