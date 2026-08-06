# Blueprint Komprehensif Aplikasi Monitoring Anak dengan Deteksi Judi, Notifikasi WhatsApp, dan Remote Lock

## Daftar Isi
1. [Tujuan dan Ringkasan](#1-tujuan-dan-ringkasan)
2. [Arsitektur Sistem](#2-arsitektur-sistem)
3. [Komponen Aplikasi Android (Client)](#3-komponen-aplikasi-android-client)
   - 3.1. Struktur Proyek dan Dependencies
   - 3.2. Izin dan AndroidManifest.xml
   - 3.3. SetupActivity (Konfigurasi Awal)
   - 3.4. ForegroundService (Menjaga Proses)
   - 3.5. UsageStatsMonitor (Deteksi Aplikasi)
   - 3.6. AccessibilityService (Deteksi URL, termasuk Incognito)
   - 3.7. VpnService (Pemblokiran Domain Judi dan DNS Logging)
   - 3.8. FirebaseMessagingService (Remote Command)
   - 3.9. DeviceAdminReceiver (Lock Screen)
   - 3.10. HTTP Client (Retrofit) dan Local Database (Room)
   - 3.11. Deteksi Status VPN dan Accessibility
4. [Backend Server (Node.js)](#4-backend-server-nodejs)
   - 4.1. Teknologi dan Struktur Folder
   - 4.2. Database Schema
   - 4.3. API Endpoint
   - 4.4. WhatsApp Bot (whatsapp-web.js)
   - 4.5. Firebase Admin (FCM)
   - 4.6. Logika Filter Judi dan Pembaruan Blocklist
5. [Fitur Khusus](#5-fitur-khusus)
   - 5.1. Notifikasi Prioritas Judi ke WhatsApp
   - 5.2. Pemblokiran Otomatis via VPN atau Lock Screen
   - 5.3. Deteksi Upaya Nonaktifkan (Heartbeat)
   - 5.4. Antisipasi VPN Anak dan Incognito
6. [Instalasi dan Deployment](#6-instalasi-dan-deployment)
   - 6.1. Build APK
   - 6.2. Instalasi via ADB
   - 6.3. Menjalankan Backend Server
7. [Kode Lengkap (Sample)](#7-kode-lengkap-sample)
   - 7.1. Android: SetupActivity.java
   - 7.2. Android: MainService.java
   - 7.3. Android: UsageStatsMonitor.java
   - 7.4. Android: URLMonitoringService.java (Accessibility)
   - 7.5. Android: MyVpnService.java (kerangka)
   - 7.6. Android: FirebaseMessagingService.java
   - 7.7. Backend: server.js
   - 7.8. Backend: wa-bot.js
8. [Kesimpulan dan Catatan Etika](#8-kesimpulan-dan-catatan-etika)

---

## 1. Tujuan dan Ringkasan
Aplikasi ini dirancang untuk dipasang di perangkat Android anak secara tersembunyi (tanpa ikon di launcher) guna memantau:
- Aplikasi apa saja yang dibuka (nama dan waktu).
- Website apa saja yang dikunjungi (URL lengkap), termasuk saat menggunakan mode incognito/private.
- Mendeteksi akses ke situs judi online berdasarkan daftar domain dan kata kunci.
- Memberikan notifikasi real-time ke WhatsApp orang tua untuk setiap aktivitas mencurigakan, dengan prioritas khusus untuk judi.
- Memblokir akses ke situs judi secara otomatis (melalui VPN lokal atau penguncian layar).
- Menerima perintah remote dari orang tua melalui WhatsApp untuk mengunci perangkat anak.
- Tetap berfungsi meskipun anak menggunakan VPN (tetap bisa mendeteksi aktivitas UI, dan memberi tahu jika VPN aktif).
- Memberi tahu orang tua jika komponen penting (AccessibilityService, VPN) dimatikan.

Blueprint ini mencakup seluruh detail teknis, arsitektur, dan potongan kode yang diperlukan untuk membangun aplikasi menggunakan Android Studio (Java) dan Node.js.

---

## 2. Arsitektur Sistem

```
┌─────────────────────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│       Perangkat Anak (Android)   │      │  Backend Server  │      │  HP Orang Tua   │
│  ┌─────────────────────────────┐ │      │   (Node.js)      │      │   (WhatsApp)    │
│  │ ForegroundService           │ │      ├──────────────────┤      ├─────────────────┤
│  │ - Menjaga proses            │ │      │ - REST API       │─────▶│ - Bot WA        │
│  │ - Scheduler                 │ │      │ - Firebase Admin │◀─────│   (Perintah)    │
│  ├─────────────────────────────┤ │ HTTP │ - WhatsApp Bot   │      │ - Notifikasi    │
│  │ UsageStatsMonitor           │◀┼─────▶│ - Database       │      └─────────────────┘
│  │ (Deteksi aplikasi)          │ │      │ - Blocklist      │
│  ├─────────────────────────────┤ │      └──────────────────┘
│  │ AccessibilityService        │ │            │ FCM
│  │ (Deteksi URL, incognito)    │ │            ▼
│  ├─────────────────────────────┤ │      ┌──────────────────┐
│  │ VpnService                  │ │      │  Firebase Cloud  │
│  │ (Blokir domain judi, DNS)   │ │      │    Messaging     │
│  ├─────────────────────────────┤ │      └──────────────────┘
│  │ FirebaseMessagingService    │◀┼──────────┘
│  │ (Terima perintah remote)    │ │
│  ├─────────────────────────────┤ │
│  │ DeviceAdminReceiver         │ │
│  │ (Lock screen)               │ │
│  ├─────────────────────────────┤ │
│  │ Room DB (Log offline)       │ │
│  │ SharedPreferences           │ │
│  └─────────────────────────────┘ │
└─────────────────────────────────┘
```

**Alur Data:**
1. **Monitoring Aplikasi**: UsageStatsMonitor mencatat aplikasi foreground setiap 2 detik. Jika berubah, simpan ke log dan kirim ke server.
2. **Monitoring Website**: AccessibilityService membaca URL dari address bar browser (termasuk incognito). Jika URL terdeteksi, dikirim ke server.
3. **Filter Judi**: Server memeriksa URL terhadap daftar domain judi dan kata kunci. Jika positif, kirim notifikasi prioritas ke WA orang tua dan perintahkan pemblokiran (jika diaktifkan).
4. **Pemblokiran**: VpnService di perangkat anak memblokir domain judi di level jaringan. Sebagai cadangan, jika VPN tidak aktif, AccessibilityService bisa memicu lock screen.
5. **Remote Command**: Orang tua mengirim pesan WA dengan format `lock <deviceId>`; bot WA memproses, server mengirim FCM ke perangkat anak, lalu DeviceAdminReceiver mengunci layar.
6. **Heartbeat**: Perangkat anak mengirim sinyal berkala ke server. Jika tidak ada selama 24 jam, server notifikasi WA.
7. **Deteksi Gangguan**: Jika AccessibilityService mati, sistem Android memanggil callback, perangkat segera kirim notifikasi ke server.

---

## 3. Komponen Aplikasi Android (Client)

### 3.1. Struktur Proyek dan Dependencies
Buat proyek baru di Android Studio dengan nama `ChildMonitor`. Gunakan bahasa Java (atau Kotlin). Minimum SDK API 21. Tambahkan dependencies di `build.gradle` (Module: app):

```groovy
dependencies {
    implementation 'androidx.appcompat:appcompat:1.6.1'
    implementation 'com.google.android.material:material:1.9.0'
    implementation 'androidx.constraintlayout:constraintlayout:2.1.4'

    // Room database
    implementation 'androidx.room:room-runtime:2.5.2'
    annotationProcessor 'androidx.room:room-compiler:2.5.2'

    // Retrofit untuk HTTP
    implementation 'com.squareup.retrofit2:retrofit:2.9.0'
    implementation 'com.squareup.retrofit2:converter-gson:2.9.0'
    implementation 'com.squareup.okhttp3:logging-interceptor:4.11.0'

    // Firebase
    implementation 'com.google.firebase:firebase-messaging:23.2.1'
    implementation 'com.google.firebase:firebase-analytics:21.3.0'

    // WorkManager untuk periodic tasks
    implementation 'androidx.work:work-runtime:2.8.1'

    // Untuk VPNService (tidak ada library khusus, pakai bawaan)
}
```

Tambahkan plugin `com.google.gms.google-services` di bagian bawah file.

### 3.2. Izin dan AndroidManifest.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="com.example.childmonitor">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />
    <uses-permission android:name="android.permission.PACKAGE_USAGE_STATS" />
    <uses-permission android:name="android.permission.BIND_ACCESSIBILITY_SERVICE" />
    <uses-permission android:name="android.permission.WAKE_LOCK" />
    <uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.KILL_BACKGROUND_PROCESSES" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />

    <application
        android:allowBackup="false"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:theme="@style/AppTheme"
        android:supportsRtl="true">

        <!-- SetupActivity tanpa launcher -->
        <activity android:name=".SetupActivity"
            android:excludeFromRecents="true"
            android:noHistory="true" />

        <!-- Foreground Service -->
        <service android:name=".MainService"
            android:enabled="true"
            android:exported="false" />

        <!-- AccessibilityService -->
        <service android:name=".URLMonitoringService"
            android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"
            android:exported="true">
            <intent-filter>
                <action android:name="android.accessibilityservice.AccessibilityService" />
            </intent-filter>
            <meta-data
                android:name="android.accessibilityservice"
                android:resource="@xml/accessibility_service_config" />
        </service>

        <!-- VpnService -->
        <service android:name=".MyVpnService"
            android:permission="android.permission.BIND_VPN_SERVICE"
            android:exported="false" />

        <!-- FirebaseMessagingService -->
        <service android:name=".MyFirebaseMessagingService"
            android:exported="false">
            <intent-filter>
                <action android:name="com.google.firebase.MESSAGING_EVENT" />
            </intent-filter>
        </service>

        <!-- DeviceAdminReceiver -->
        <receiver android:name=".AdminReceiver"
            android:permission="android.permission.BIND_DEVICE_ADMIN">
            <meta-data
                android:name="android.app.device_admin"
                android:resource="@xml/device_admin_receiver" />
            <intent-filter>
                <action android:name="android.app.action.DEVICE_ADMIN_ENABLED" />
            </intent-filter>
        </receiver>

        <!-- Broadcast Receiver untuk boot -->
        <receiver android:name=".BootReceiver"
            android:enabled="true"
            android:exported="false">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED" />
            </intent-filter>
        </receiver>

    </application>
</manifest>
```

File konfigurasi aksesibilitas: `res/xml/accessibility_service_config.xml`
```xml
<?xml version="1.0" encoding="utf-8"?>
<accessibility-service xmlns:android="http://schemas.android.com/apk/res/android"
    android:description="@string/accessibility_service_description"
    android:accessibilityEventTypes="typeWindowStateChanged|typeWindowContentChanged"
    android:accessibilityFlags="flagReportViewIds|flagRetrieveInteractiveWindows"
    android:canRetrieveWindowContent="true"
    android:notificationTimeout="100"
    android:settingsActivity="" />
```

File device admin: `res/xml/device_admin_receiver.xml`
```xml
<device-admin xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-policies>
        <force-lock />
    </uses-policies>
</device-admin>
```

### 3.3. SetupActivity (Konfigurasi Awal)
Activity ini dipanggil via ADB setelah instalasi. Fungsinya:
- Meminta input nomor WhatsApp orang tua.
- Meminta aktivasi izin UsageStats (buka halaman settings).
- Meminta aktivasi AccessibilityService.
- Meminta aktivasi Device Admin.
- Meminta izin abaikan optimasi baterai.
- Mendapatkan FCM token dan mendaftarkannya ke server.
- Menyimpan konfigurasi ke SharedPreferences.

```java
public class SetupActivity extends AppCompatActivity {
    private EditText etWaNumber;
    private Button btnSave;
    private SharedPreferences prefs;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_setup);

        prefs = getSharedPreferences("config", MODE_PRIVATE);
        etWaNumber = findViewById(R.id.et_wa_number);
        btnSave = findViewById(R.id.btn_save);

        btnSave.setOnClickListener(v -> {
            String waNumber = etWaNumber.getText().toString().trim();
            if (waNumber.isEmpty()) return;
            prefs.edit().putString("wa_number", waNumber).apply();

            // Minta izin UsageStats
            startActivity(new Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS));

            // Minta aksesibilitas
            Intent intent = new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS);
            startActivity(intent);

            // Minta device admin
            ComponentName admin = new ComponentName(this, AdminReceiver.class);
            Intent intentAdmin = new Intent(DevicePolicyManager.ACTION_ADD_DEVICE_ADMIN);
            intentAdmin.putExtra(DevicePolicyManager.EXTRA_DEVICE_ADMIN, admin);
            intentAdmin.putExtra(DevicePolicyManager.EXTRA_ADD_EXPLANATION, "Digunakan untuk mengunci layar dari jarak jauh");
            startActivityForResult(intentAdmin, 100);

            // Minta abaikan optimasi baterai
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                Intent intentBattery = new Intent();
                String packageName = getPackageName();
                if (!((PowerManager) getSystemService(POWER_SERVICE)).isIgnoringBatteryOptimizations(packageName)) {
                    intentBattery.setAction(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
                    intentBattery.setData(Uri.parse("package:" + packageName));
                    startActivity(intentBattery);
                }
            }

            // Dapatkan token FCM (implementasi di bawah)
            FirebaseMessaging.getInstance().getToken()
                .addOnCompleteListener(task -> {
                    if (task.isSuccessful()) {
                        String token = task.getResult();
                        registerToServer(waNumber, token);
                    }
                });

            Toast.makeText(this, "Pengaturan selesai. Aplikasi akan berjalan di background.", Toast.LENGTH_LONG).show();
            finish();
        });
    }

    private void registerToServer(String waNumber, String token) {
        // Panggil API /register (lihat bagian backend)
        RetrofitClient.getInstance().getApi().register(deviceId, waNumber, token)
            .enqueue(new Callback<Void>() { ... });
    }
}
```

**Catatan**: `deviceId` bisa dihasilkan dari `Settings.Secure.ANDROID_ID` atau UUID.randomUUID() yang disimpan.

### 3.4. ForegroundService (MainService)
Service ini berjalan terus-menerus, menampilkan notifikasi, dan menjadwalkan pengecekan aplikasi.

```java
public class MainService extends Service {
    private static final int NOTIF_ID = 1001;
    private Handler handler = new Handler();
    private Runnable checkAppTask = new Runnable() {
        @Override
        public void run() {
            // Panggil UsageStatsMonitor untuk deteksi aplikasi
            String currentApp = UsageStatsMonitor.getForegroundApp(MainService.this);
            if (!currentApp.equals(lastApp)) {
                sendAppLog(currentApp);
                lastApp = currentApp;
            }
            handler.postDelayed(this, 2000);
        }
    };
    private String lastApp = "";

    @Override
    public void onCreate() {
        super.onCreate();
        startForeground();
        handler.post(checkAppTask);
    }

    private void startForeground() {
        Notification notification = new NotificationCompat.Builder(this, "monitor_channel")
                .setContentTitle("Layanan Sistem")
                .setContentText("Berjalan di latar belakang")
                .setSmallIcon(R.drawable.ic_notification)
                .setPriority(NotificationCompat.PRIORITY_MIN)
                .build();
        startForeground(NOTIF_ID, notification);
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        handler.removeCallbacks(checkAppTask);
        super.onDestroy();
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }
}
```

### 3.5. UsageStatsMonitor (Deteksi Aplikasi)
Kelas utility untuk mendapatkan aplikasi foreground.

```java
public class UsageStatsMonitor {
    public static String getForegroundApp(Context context) {
        String currentApp = null;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            UsageStatsManager usm = (UsageStatsManager) context.getSystemService(Context.USAGE_STATS_SERVICE);
            long time = System.currentTimeMillis();
            List<UsageStats> stats = usm.queryUsageStats(UsageStatsManager.INTERVAL_DAILY, time - 1000 * 60, time);
            if (stats != null) {
                SortedMap<Long, UsageStats> sortedMap = new TreeMap<>();
                for (UsageStats usageStats : stats) {
                    sortedMap.put(usageStats.getLastTimeUsed(), usageStats);
                }
                if (!sortedMap.isEmpty()) {
                    currentApp = sortedMap.get(sortedMap.lastKey()).getPackageName();
                }
            }
        }
        return currentApp != null ? currentApp : "";
    }
}
```

### 3.6. AccessibilityService (URLMonitoringService)
Service ini mendeteksi perubahan jendela dan membaca URL dari browser.

```java
public class URLMonitoringService extends AccessibilityService {
    private static final Map<String, String> BROWSER_URL_BAR_IDS = new HashMap<>();
    static {
        BROWSER_URL_BAR_IDS.put("com.android.chrome", "com.android.chrome:id/url_bar");
        BROWSER_URL_BAR_IDS.put("org.mozilla.firefox", "org.mozilla.firefox:id/url_bar");
        BROWSER_URL_BAR_IDS.put("com.incognito.browser", "com.incognito.browser:id/address_bar");
        BROWSER_URL_BAR_IDS.put("org.mozilla.focus", "org.mozilla.focus:id/url_view");
        BROWSER_URL_BAR_IDS.put("com.duckduckgo.mobile.android", "com.duckduckgo.mobile.android:id/omnibarTextInput");
        // tambahkan lainnya
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event.getEventType() == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            String packageName = event.getPackageName() != null ? event.getPackageName().toString() : "";
            if (isBrowser(packageName)) {
                AccessibilityNodeInfo root = getRootInActiveWindow();
                String url = findUrlFromRoot(root, packageName);
                if (url != null && !url.isEmpty()) {
                    // Kirim ke server
                    sendUrlLog(packageName, url);
                    // Cek apakah judi
                    if (JudiFilter.isJudiSite(url)) {
                        // Tindakan: notifikasi prioritas + blokir
                        handleJudiDetected(url);
                    }
                }
            }
        }
    }

    private boolean isBrowser(String packageName) {
        return packageName.contains("browser") || packageName.contains("chrome") ||
                packageName.contains("firefox") || packageName.contains("opera") ||
                BROWSER_URL_BAR_IDS.containsKey(packageName);
    }

    private String findUrlFromRoot(AccessibilityNodeInfo root, String packageName) {
        if (root == null) return null;
        // Cari berdasarkan ID yang dikenal
        String resourceId = BROWSER_URL_BAR_IDS.get(packageName);
        if (resourceId != null) {
            List<AccessibilityNodeInfo> nodes = root.findAccessibilityNodeInfosByViewId(resourceId);
            if (nodes != null && !nodes.isEmpty()) {
                CharSequence text = nodes.get(0).getText();
                return text != null ? text.toString() : null;
            }
        }
        // Fallback: cari node EditText dengan hint address
        return findAddressBarFallback(root);
    }

    private String findAddressBarFallback(AccessibilityNodeInfo node) {
        if (node == null) return null;
        if (node.getClassName().equals("android.widget.EditText")) {
            CharSequence text = node.getText();
            if (text != null && (text.toString().startsWith("http") || text.toString().contains("."))) {
                return text.toString();
            }
        }
        for (int i = 0; i < node.getChildCount(); i++) {
            String result = findAddressBarFallback(node.getChild(i));
            if (result != null) return result;
        }
        return null;
    }

    private void sendUrlLog(String packageName, String url) {
        // Simpan ke DB dan kirim ke server
        LogEntry entry = new LogEntry(packageName, getAppName(packageName), url, System.currentTimeMillis());
        AppDatabase.getInstance(this).logDao().insert(entry);
        // Trigger pengiriman (via WorkManager atau langsung)
    }

    private void handleJudiDetected(String url) {
        // Kirim notifikasi prioritas ke server (dengan flag judi=true)
        // Jika VPN aktif, biarkan VPN memblokir; jika tidak, lakukan lock atau back
        if (!VpnStatus.isVpnActive(this)) {
            // Opsi: lock screen
            lockDevice();
            // Atau tekan back
            performGlobalAction(GLOBAL_ACTION_BACK);
        }
    }

    private void lockDevice() {
        DevicePolicyManager dpm = (DevicePolicyManager) getSystemService(DEVICE_POLICY_SERVICE);
        ComponentName admin = new ComponentName(this, AdminReceiver.class);
        if (dpm.isAdminActive(admin)) {
            dpm.lockNow();
        }
    }

    @Override
    public void onInterrupt() {
        // Service dimatikan, kirim notifikasi ke server
        notifyAccessibilityDisabled();
    }

    private void notifyAccessibilityDisabled() {
        // Panggil API untuk memberi tahu bahwa aksesibilitas mati
    }
}
```

### 3.7. VpnService (MyVpnService) untuk Pemblokiran Domain Judi
Service ini membuat VPN lokal yang memfilter koneksi berdasarkan domain. Karena kompleks, kita berikan kerangka dasar. Untuk implementasi lengkap, Anda bisa menggunakan library seperti `VpnService` dari `ibrahimtnc` atau menulis manual dengan tun2socks.

```java
public class MyVpnService extends VpnService {
    private Thread mThread;
    private ParcelFileDescriptor mInterface;
    private volatile boolean running = true;
    private Set<String> blockedDomains = new CopyOnWriteArraySet<>();

    @Override
    public void onCreate() {
        super.onCreate();
        loadBlockedDomains();
    }

    private void loadBlockedDomains() {
        // Ambil dari SharedPreferences atau download dari server
        blockedDomains.addAll(Arrays.asList("sbobet.com", "ibcbet.com", ...));
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        startVpn();
        return START_STICKY;
    }

    private void startVpn() {
        if (mThread != null) return;
        mThread = new Thread(() -> {
            try {
                Builder builder = new Builder();
                builder.setSession("Child Monitor")
                        .addAddress("10.0.0.2", 32)
                        .addRoute("0.0.0.0", 0)
                        .addDnsServer("8.8.8.8");
                mInterface = builder.establish();
                if (mInterface == null) return;

                // Baca paket dari TUN dan filter DNS
                FileInputStream in = new FileInputStream(mInterface.getFileDescriptor());
                // Loop pembacaan paket
                byte[] packet = new byte[32767];
                while (running) {
                    int length = in.read(packet);
                    if (length <= 0) break;
                    // Proses paket: jika DNS query, ekstrak domain dan blokir jika perlu
                    if (isDnsPacket(packet, length)) {
                        String domain = extractDomainFromDns(packet, length);
                        if (domain != null && isBlocked(domain)) {
                            // Jangan teruskan paket (abort)
                            continue;
                        }
                    }
                    // Teruskan paket ke internet (perlu implementasi forwarding)
                    forwardPacket(packet, length);
                }
            } catch (Exception e) {
                e.printStackTrace();
            }
        });
        mThread.start();
    }

    private boolean isDnsPacket(byte[] packet, int length) {
        // Implementasi sederhana: periksa port tujuan 53
        // ...
        return false;
    }

    private String extractDomainFromDns(byte[] packet, int length) {
        // Parsing DNS query
        // ...
        return null;
    }

    private boolean isBlocked(String domain) {
        for (String blocked : blockedDomains) {
            if (domain.equals(blocked) || domain.endsWith("." + blocked)) {
                return true;
            }
        }
        return false;
    }

    private void forwardPacket(byte[] packet, int length) {
        // Di sini perlu koneksi keluar, misal dengan socket raw.
        // Untuk kemudahan, integrasikan dengan library seperti tun2socks.
    }

    @Override
    public void onDestroy() {
        running = false;
        if (mThread != null) mThread.interrupt();
        if (mInterface != null) try { mInterface.close(); } catch (IOException e) {}
        super.onDestroy();
    }
}
```

**Alternatif**: Gunakan library [VpnService Library](https://github.com/ibrahimtnc/VpnService) yang menyediakan contoh lengkap.

### 3.8. FirebaseMessagingService (Menerima Perintah Remote)
```java
public class MyFirebaseMessagingService extends FirebaseMessagingService {
    @Override
    public void onMessageReceived(RemoteMessage remoteMessage) {
        if (remoteMessage.getData().containsKey("command")) {
            String command = remoteMessage.getData().get("command");
            if ("lock".equals(command)) {
                // Kunci layar
                DevicePolicyManager dpm = (DevicePolicyManager) getSystemService(DEVICE_POLICY_SERVICE);
                ComponentName admin = new ComponentName(this, AdminReceiver.class);
                if (dpm.isAdminActive(admin)) {
                    dpm.lockNow();
                }
            }
        }
    }

    @Override
    public void onNewToken(String token) {
        // Kirim token baru ke server
        String deviceId = getSharedPreferences("config", MODE_PRIVATE).getString("device_id", "");
        String waNumber = getSharedPreferences("config", MODE_PRIVATE).getString("wa_number", "");
        RetrofitClient.getInstance().getApi().register(deviceId, waNumber, token).enqueue(...);
    }
}
```

### 3.9. DeviceAdminReceiver
```java
public class AdminReceiver extends DeviceAdminReceiver {
    @Override
    public void onEnabled(Context context, Intent intent) {
        super.onEnabled(context, intent);
        // Admin diaktifkan
    }

    @Override
    public void onDisabled(Context context, Intent intent) {
        super.onDisabled(context, intent);
        // Admin dinonaktifkan, kirim notifikasi ke server
    }
}
```

### 3.10. HTTP Client (Retrofit) dan Local Database (Room)

#### a. RetrofitClient
```java
public class RetrofitClient {
    private static final String BASE_URL = "https://api.parentmonitor.com/"; // ganti dengan URL server
    private static Retrofit retrofit;

    public static ApiService getInstance() {
        if (retrofit == null) {
            retrofit = new Retrofit.Builder()
                    .baseUrl(BASE_URL)
                    .addConverterFactory(GsonConverterFactory.create())
                    .build();
        }
        return retrofit.create(ApiService.class);
    }
}

public interface ApiService {
    @POST("api/register")
    Call<Void> register(@Body RegisterRequest request);

    @POST("api/log")
    Call<Void> sendLog(@Body LogData logData);

    @GET("api/blocklist")
    Call<BlocklistResponse> getBlocklist();
}
```

#### b. Room Database
Entity `LogEntry`:
```java
@Entity
public class LogEntry {
    @PrimaryKey(autoGenerate = true)
    public int id;
    public String packageName;
    public String appName;
    public String url;
    public long timestamp;
    public boolean sent;
    public boolean isJudi; // flag untuk prioritas
}

@Dao
public interface LogDao {
    @Insert
    void insert(LogEntry entry);

    @Query("SELECT * FROM LogEntry WHERE sent = 0 ORDER BY timestamp ASC")
    List<LogEntry> getUnsentLogs();

    @Update
    void update(LogEntry entry);
}

@Database(entities = {LogEntry.class}, version = 1)
public abstract class AppDatabase extends RoomDatabase {
    public abstract LogDao logDao();

    private static AppDatabase INSTANCE;
    public static AppDatabase getInstance(Context context) {
        if (INSTANCE == null) {
            INSTANCE = Room.databaseBuilder(context.getApplicationContext(),
                            AppDatabase.class, "monitor.db")
                    .build();
        }
        return INSTANCE;
    }
}
```

#### c. WorkManager untuk Mengirim Log Periodik
Buat Worker yang mengirim log yang belum terkirim:

```java
public class LogSenderWorker extends Worker {
    public LogSenderWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    @NonNull
    @Override
    public Result doWork() {
        AppDatabase db = AppDatabase.getInstance(getApplicationContext());
        List<LogEntry> unsent = db.logDao().getUnsentLogs();
        for (LogEntry entry : unsent) {
            boolean success = sendToServer(entry);
            if (success) {
                entry.sent = true;
                db.logDao().update(entry);
            } else {
                // Gagal, coba lagi nanti
            }
        }
        return Result.success();
    }

    private boolean sendToServer(LogEntry entry) {
        try {
            Response<Void> response = RetrofitClient.getInstance().sendLog(entry).execute();
            return response.isSuccessful();
        } catch (IOException e) {
            return false;
        }
    }
}
```

Jadwalkan worker setiap 5 menit (atau interval lain) di MainService.

### 3.11. Deteksi Status VPN dan Accessibility
Buat class utility untuk mengecek apakah VPN aktif:
```java
public class VpnStatus {
    public static boolean isVpnActive(Context context) {
        ConnectivityManager cm = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
        Network[] networks = cm.getAllNetworks();
        for (Network network : networks) {
            NetworkCapabilities caps = cm.getNetworkCapabilities(network);
            if (caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) {
                return true;
            }
        }
        return false;
    }
}
```

Untuk mendeteksi jika AccessibilityService mati, kita sudah punya callback `onInterrupt()`. Juga bisa mengecek secara periodik apakah service masih terdaftar dengan `AccessibilityManager`.

---

## 4. Backend Server (Node.js)

### 4.1. Teknologi dan Struktur Folder
- **Runtime**: Node.js
- **Framework**: Express
- **Database**: MySQL atau SQLite (untuk sederhana, gunakan SQLite)
- **WhatsApp Bot**: whatsapp-web.js
- **FCM**: firebase-admin
- **Struktur folder**:
```
backend/
├── index.js                (entry point)
├── routes/
│   └── api.js
├── controllers/
│   ├── deviceController.js
│   ├── logController.js
│   └── blocklistController.js
├── models/
│   └── db.js               (koneksi database)
├── services/
│   ├── waBot.js
│   └── fcm.js
├── utils/
│   └── judiFilter.js
└── package.json
```

### 4.2. Database Schema
Gunakan SQLite untuk kemudahan. Buat file `database.sqlite` dengan tabel:

```sql
CREATE TABLE devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT UNIQUE NOT NULL,
    fcm_token TEXT,
    wa_number TEXT NOT NULL,
    last_heartbeat INTEGER,
    created_at INTEGER
);

CREATE TABLE logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    package_name TEXT,
    app_name TEXT,
    url TEXT,
    timestamp INTEGER,
    is_judi INTEGER DEFAULT 0,
    sent_wa INTEGER DEFAULT 0,
    FOREIGN KEY(device_id) REFERENCES devices(device_id)
);

CREATE TABLE blocklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT UNIQUE NOT NULL,
    added_at INTEGER
);
```

### 4.3. API Endpoint

#### `POST /api/register`
Request body:
```json
{
  "deviceId": "...",
  "waNumber": "...",
  "fcmToken": "..."
}
```
Response: 200 OK

#### `POST /api/log`
Request body:
```json
{
  "deviceId": "...",
  "packageName": "...",
  "appName": "...",
  "url": "...",
  "timestamp": 1234567890,
  "isJudi": false
}
```
- Simpan log ke database.
- Jika `isJudi` true, langsung kirim notifikasi WA prioritas.
- Jika tidak, kirim WA biasa (bisa dibatasi frekuensinya).

#### `GET /api/blocklist`
Response:
```json
{
  "domains": ["sbobet.com", "newjudi.xyz"],
  "keywords": ["judi", "slot", "poker"],
  "version": 1
}
```

#### `POST /api/heartbeat`
Dari perangkat setiap 6 jam. Body: `{ deviceId }`. Update `last_heartbeat`.

### 4.4. WhatsApp Bot (waBot.js)
```javascript
const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');

const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: { headless: true }
});

client.on('qr', (qr) => {
    qrcode.generate(qr, { small: true });
    console.log('Scan QR code dengan WhatsApp Anda');
});

client.on('ready', () => {
    console.log('WhatsApp bot siap');
});

client.on('message', async message => {
    const chat = await message.getChat();
    const sender = message.from; // format: 628xxx@c.us

    // Perintah: lock <deviceId>
    if (message.body.startsWith('lock ')) {
        const deviceId = message.body.split(' ')[1];
        // Validasi apakah sender terdaftar sebagai orang tua untuk device tersebut
        const device = await getDeviceByWA(sender);
        if (device && device.device_id === deviceId) {
            // Kirim FCM
            await sendFCM(deviceId, 'lock');
            await message.reply('Perintah lock telah dikirim');
        } else {
            await message.reply('Anda tidak berhak mengunci perangkat ini');
        }
    }

    // Perintah: status <deviceId>
    // dll.
});

// Fungsi mengirim notifikasi log ke WA
async function sendLogToWA(waNumber, logData, isJudi = false) {
    const prefix = isJudi ? '🚨 PERINGATAN! ' : '🔔 ';
    const message = `${prefix}Aktivitas Anak\nAplikasi: ${logData.appName || logData.packageName}\n` +
        (logData.url ? `URL: ${logData.url}\n` : '') +
        `Waktu: ${new Date(logData.timestamp).toLocaleString()}`;
    await client.sendMessage(waNumber + '@c.us', message);
}

module.exports = { client, sendLogToWA };
```

### 4.5. Firebase Admin (FCM)
```javascript
const admin = require('firebase-admin');
const serviceAccount = require('./serviceAccountKey.json');

admin.initializeApp({
    credential: admin.credential.cert(serviceAccount)
});

async function sendFCM(deviceId, command) {
    const device = await getDeviceById(deviceId);
    if (!device || !device.fcm_token) return;
    const message = {
        data: { command: command },
        token: device.fcm_token
    };
    try {
        await admin.messaging().send(message);
    } catch (error) {
        console.error('FCM error:', error);
    }
}
```

### 4.6. Logika Filter Judi dan Pembaruan Blocklist
```javascript
const judiDomains = require('./judi-domains.json'); // daftar statis awal

function isJudiSite(url) {
    try {
        const host = new URL(url).hostname;
        // Cek exact match
        if (judiDomains.includes(host)) return true;
        // Cek subdomain
        const parts = host.split('.');
        if (parts.length >= 2) {
            const baseDomain = parts.slice(-2).join('.');
            if (judiDomains.includes(baseDomain)) return true;
        }
        // Cek kata kunci
        const urlLower = url.toLowerCase();
        const keywords = ['judi', 'slot', 'poker', 'togel', 'casino', 'bet', 'bola'];
        return keywords.some(k => urlLower.includes(k));
    } catch (e) {
        return false;
    }
}

// Endpoint untuk memperbarui blocklist (bisa dijalankan cron job)
async function updateBlocklist() {
    // Ambil dari sumber eksternal misal API Kominfo atau crowdsource
    const newDomains = await fetch('https://some-source.com/judi.txt');
    // Simpan ke database
}
```

---

## 5. Fitur Khusus

### 5.1. Notifikasi Prioritas Judi ke WhatsApp
- Saat log masuk dengan `isJudi = true`, server segera panggil `sendLogToWA` dengan prefix 🚨.
- Bisa ditambahkan tindakan otomatis: jika terdeteksi judi, server juga mengirim FCM `block` ke perangkat (untuk memicu VPN atau lock).

### 5.2. Pemblokiran Otomatis via VPN atau Lock Screen
- **Jika VPN aktif**: VpnService memblokir domain di level jaringan (koneksi gagal).
- **Jika VPN tidak aktif**: Saat AccessibilityService mendeteksi URL judi, ia bisa langsung melakukan `performGlobalAction(GLOBAL_ACTION_BACK)` untuk menutup tab, atau `lockDevice()`.
- Opsi lainnya: Server bisa mengirim perintah `lock` ke perangkat saat menerima log judi.

### 5.3. Deteksi Upaya Nonaktifkan (Heartbeat)
- Perangkat mengirim heartbeat setiap 6 jam ke `POST /api/heartbeat`.
- Jika server tidak menerima heartbeat dari suatu device selama >24 jam, kirim notifikasi WA ke nomor orang tua bahwa perangkat mungkin tidak terpantau.
- Demikian pula, jika AccessibilityService mati, perangkat segera mengirim notifikasi (via HTTP) ke server.

### 5.4. Antisipasi VPN Anak dan Incognito
- **Deteksi VPN anak**: `VpnStatus.isVpnActive()` di perangkat. Jika true, tambahkan flag `vpn_active` di log atau kirim notifikasi terpisah ke WA.
- **Incognito**: AccessibilityService tetap bisa membaca URL dari address bar, karena tidak ada perbedaan UI.
- **Browser yang tidak mengekspos URL**: VpnService mencatat semua permintaan DNS, sehingga setidaknya domain dapat diketahui.

---

## 6. Instalasi dan Deployment

### 6.1. Build APK
- Di Android Studio, Generate Signed APK.
- Pastikan minify tidak diaktifkan (atau atur proguard agar tidak menghapus kelas penting).
- Hasil APK: `app-release.apk`.

### 6.2. Instalasi via ADB
```bash
# Install APK
adb install app-release.apk

# Beri izin UsageStats
adb shell pm grant com.example.childmonitor android.permission.PACKAGE_USAGE_STATS

# Jalankan SetupActivity
adb shell am start -n com.example.childmonitor/.SetupActivity

# Matikan optimasi baterai
adb shell dumpsys deviceidle whitelist +com.example.childmonitor

# Opsional: Sembunyikan notifikasi? Tidak bisa, tapi bisa dibuat tidak mencolok.
```

Setelah SetupActivity selesai, aplikasi akan berjalan di background. Tidak ada ikon di launcher.

### 6.3. Menjalankan Backend Server
```bash
cd backend
npm install
npm install -g pm2 (opsional)
node index.js
```
Server berjalan di port 3000. Pastikan domain dan firewall dikonfigurasi.

---

## 7. Kode Lengkap (Sample)

### 7.1. SetupActivity.java (sudah di atas)
### 7.2. MainService.java (sudah di atas)
### 7.3. UsageStatsMonitor.java (sudah di atas)
### 7.4. URLMonitoringService.java (sudah di atas)
### 7.5. MyVpnService.java (kerangka di atas, perlu implementasi lengkap)
### 7.6. MyFirebaseMessagingService.java (sudah di atas)

### 7.7. Backend: server.js (sederhana)
```javascript
const express = require('express');
const bodyParser = require('body-parser');
const sqlite3 = require('sqlite3').verbose();
const { sendLogToWA } = require('./services/waBot');
const { sendFCM } = require('./services/fcm');
const { isJudiSite } = require('./utils/judiFilter');

const app = express();
app.use(bodyParser.json());

const db = new sqlite3.Database('./database.sqlite');

// Middleware untuk CORS
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept');
    next();
});

// Register
app.post('/api/register', (req, res) => {
    const { deviceId, waNumber, fcmToken } = req.body;
    const now = Date.now();
    db.run(`INSERT OR REPLACE INTO devices (device_id, wa_number, fcm_token, last_heartbeat, created_at)
            VALUES (?, ?, ?, ?, ?)`,
        [deviceId, waNumber, fcmToken, now, now],
        function(err) {
            if (err) return res.status(500).send(err.message);
            res.sendStatus(200);
        });
});

// Log
app.post('/api/log', (req, res) => {
    const { deviceId, packageName, appName, url, timestamp, isJudi } = req.body;
    // Simpan log
    db.run(`INSERT INTO logs (device_id, package_name, app_name, url, timestamp, is_judi)
            VALUES (?, ?, ?, ?, ?, ?)`,
        [deviceId, packageName, appName, url, timestamp, isJudi ? 1 : 0],
        async function(err) {
            if (err) return res.status(500).send(err.message);
            // Dapatkan nomor WA device
            db.get(`SELECT wa_number FROM devices WHERE device_id = ?`, [deviceId], async (err, row) => {
                if (row) {
                    await sendLogToWA(row.wa_number, { appName, packageName, url, timestamp }, isJudi);
                }
            });
            res.sendStatus(200);
        });
});

// Blocklist
app.get('/api/blocklist', (req, res) => {
    db.all(`SELECT domain FROM blocklist`, [], (err, rows) => {
        if (err) return res.status(500).send(err.message);
        const domains = rows.map(r => r.domain);
        const keywords = ['judi', 'slot', 'poker', 'togel', 'casino', 'bet'];
        res.json({ domains, keywords, version: 1 });
    });
});

// Heartbeat
app.post('/api/heartbeat', (req, res) => {
    const { deviceId } = req.body;
    db.run(`UPDATE devices SET last_heartbeat = ? WHERE device_id = ?`, [Date.now(), deviceId]);
    res.sendStatus(200);
});

app.listen(3000, () => console.log('Server running on port 3000'));
```

### 7.8. Backend: wa-bot.js (sudah di atas)

---

## 8. Kesimpulan dan Catatan Etika

Blueprint ini memberikan panduan lengkap untuk membangun aplikasi monitoring anak yang canggih, mencakup deteksi aplikasi dan website, notifikasi WhatsApp real-time, filter judi, pemblokiran otomatis, dan ketahanan terhadap upaya evasi seperti VPN dan incognito.

**Cat Penting**:
- Pastikan penggunaan aplikasi ini sesuai dengan hukum setempat dan dengan sepengetahuan anak jika sudah cukup umur. Idealnya, gunakan sebagai alat perlindungan dan komunikasi, bukan sebagai alat pengawasan tanpa persetujuan.
- Aplikasi ini membutuhkan banyak izin sensitif; jelaskan kepada orang tua yang memasang bahwa mereka harus mengaktifkannya secara manual melalui ADB atau setup activity.
- Performa baterai mungkin terpengaruh karena VPN dan service berjalan terus; optimasi dengan interval yang lebih panjang jika perlu.
- WhatsApp Bot menggunakan whatsapp-web.js yang tidak resmi; bisa saja akun WhatsApp diblokir jika digunakan secara tidak wajar. Gunakan nomor khusus untuk bot.

Dengan mengikuti blueprint ini, Anda dapat membangun sistem monitoring yang handal. Selamat mencoba!