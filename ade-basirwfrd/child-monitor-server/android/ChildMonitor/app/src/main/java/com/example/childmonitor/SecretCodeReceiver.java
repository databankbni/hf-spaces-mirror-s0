package com.example.childmonitor;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/**
 * Membuka layar setup saat kode rahasia ditekan di aplikasi Telepon (tanpa USB).
 * Contoh: *#*#818181#*#* — angka harus sama dengan android:host di manifest.
 * Di beberapa OEM (tertentu) fitur ini dibatasi; gunakan deep link childmonitor://setup sebagai cadangan.
 */
public class SecretCodeReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        Intent open = new Intent(context, SetupActivity.class);
        open.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        context.startActivity(open);
    }
}
