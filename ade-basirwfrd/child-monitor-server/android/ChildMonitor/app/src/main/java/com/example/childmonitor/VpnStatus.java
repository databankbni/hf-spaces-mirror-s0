package com.example.childmonitor;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.os.Build;

public class VpnStatus {

    /**
     * VPN pihak ketiga (bukan {@link MyVpnService} kita) — untuk alert orang tua.
     */
    public static boolean isThirdPartyVpnActive(Context context) {
        return isVpnActive(context) && !MyVpnService.isOurSessionActive();
    }

    /**
     * Ada transport VPN aktif (termasuk VPN internal app jika sedang establish).
     */
    public static boolean isVpnActive(Context context) {
        try {
            ConnectivityManager cm = (ConnectivityManager) context.getSystemService(Context.CONNECTIVITY_SERVICE);
            if (cm == null) return false;

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                Network[] networks = cm.getAllNetworks();
                for (Network network : networks) {
                    NetworkCapabilities caps = cm.getNetworkCapabilities(network);
                    if (caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) {
                        return true;
                    }
                }
            }
        } catch (Exception e) {
            // Ignore
        }
        return false;
    }
}
