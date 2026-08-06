package com.example.childmonitor;

import android.content.Intent;
import android.net.VpnService;
import android.os.ParcelFileDescriptor;

import java.io.FileInputStream;
import java.io.IOException;
import java.util.Arrays;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArraySet;

/**
 * VPN Service for blocking gambling domains at network level.
 * 
 * NOTE: This is a framework/skeleton implementation.
 * Full packet forwarding requires additional libraries like tun2socks.
 * The DNS-based blocking logic is scaffolded but needs complete implementation.
 */
public class MyVpnService extends VpnService {

    /** True saat TUN aktif — dipakai agar alert "VPN anak" tidak memicu saat VPN internal kita yang jalan. */
    private static volatile boolean sOurSessionActive;

    public static boolean isOurSessionActive() {
        return sOurSessionActive;
    }

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
        // Load from SharedPreferences or download from server
        blockedDomains.addAll(Arrays.asList(
                "sbobet.com", "ibcbet.com", "maxbet.com", "188bet.com",
                "bet365.com", "1xbet.com", "22bet.com", "melbet.com",
                "poker88.com", "idnpoker.com", "dewapoker.com",
                "togel.com", "togel4d.com", "totobet.com",
                "slot88.com", "joker123.com", "joker388.com",
                "judionline.com", "judibola.com", "slotgacor.com"
        ));

        // TODO: Also fetch from server API /api/blocklist
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
                builder.setSession("Child Monitor VPN")
                        .addAddress("10.0.0.2", 32)
                        .addRoute("0.0.0.0", 0)
                        .addDnsServer("8.8.8.8")
                        .addDnsServer("8.8.4.4");

                mInterface = builder.establish();
                if (mInterface == null) {
                    sOurSessionActive = false;
                    return;
                }
                sOurSessionActive = true;

                // Read packets from TUN interface and filter DNS
                FileInputStream in = new FileInputStream(mInterface.getFileDescriptor());
                byte[] packet = new byte[32767];

                while (running) {
                    int length = in.read(packet);
                    if (length <= 0) break;

                    // Process packet: if DNS query, extract domain and block if needed
                    if (isDnsPacket(packet, length)) {
                        String domain = extractDomainFromDns(packet, length);
                        if (domain != null && isBlocked(domain)) {
                            // Don't forward this packet - effectively blocks the domain
                            continue;
                        }
                    }

                    // Forward packet to internet
                    // TODO: Implement full packet forwarding with tun2socks or similar
                    forwardPacket(packet, length);
                }
            } catch (Exception e) {
                e.printStackTrace();
            }
        });
        mThread.start();
    }

    /**
     * Check if packet is a DNS query (destination port 53)
     * Simplified check - needs proper IP/UDP header parsing for production
     */
    private boolean isDnsPacket(byte[] packet, int length) {
        if (length < 28) return false; // Minimum IP + UDP header size

        // Check IP version (4)
        int version = (packet[0] >> 4) & 0xF;
        if (version != 4) return false;

        // Check protocol (17 = UDP)
        int protocol = packet[9] & 0xFF;
        if (protocol != 17) return false;

        // Get IP header length
        int ihl = (packet[0] & 0xF) * 4;

        // Check destination port (should be 53 for DNS)
        int destPort = ((packet[ihl + 2] & 0xFF) << 8) | (packet[ihl + 3] & 0xFF);
        return destPort == 53;
    }

    /**
     * Extract domain name from DNS query packet
     * Simplified implementation - needs proper DNS parsing for production
     */
    private String extractDomainFromDns(byte[] packet, int length) {
        try {
            // IP header length
            int ihl = (packet[0] & 0xF) * 4;
            // UDP header is 8 bytes
            int dnsStart = ihl + 8;

            // DNS header is 12 bytes, question starts after
            int questionStart = dnsStart + 12;
            if (questionStart >= length) return null;

            // Parse domain name from DNS question
            StringBuilder domain = new StringBuilder();
            int pos = questionStart;
            while (pos < length && packet[pos] != 0) {
                int labelLength = packet[pos] & 0xFF;
                if (labelLength == 0) break;
                pos++;
                if (domain.length() > 0) domain.append('.');
                for (int i = 0; i < labelLength && pos < length; i++, pos++) {
                    domain.append((char) (packet[pos] & 0xFF));
                }
            }

            return domain.length() > 0 ? domain.toString().toLowerCase() : null;
        } catch (Exception e) {
            return null;
        }
    }

    /**
     * Check if a domain is in the blocklist
     */
    private boolean isBlocked(String domain) {
        for (String blocked : blockedDomains) {
            if (domain.equals(blocked) || domain.endsWith("." + blocked)) {
                return true;
            }
        }
        return false;
    }

    /**
     * Forward packet to internet
     * TODO: This needs a proper implementation with socket forwarding or tun2socks
     */
    private void forwardPacket(byte[] packet, int length) {
        // Placeholder - needs implementation
        // Options:
        // 1. Use tun2socks library for full TCP/IP stack
        // 2. Use raw sockets (requires root on some devices)
        // 3. Use DatagramSocket for UDP forwarding
    }

    /**
     * Update the blocklist from server
     */
    public void updateBlocklist(Set<String> newDomains) {
        blockedDomains.clear();
        blockedDomains.addAll(newDomains);
    }

    @Override
    public void onDestroy() {
        running = false;
        sOurSessionActive = false;
        if (mThread != null) mThread.interrupt();
        if (mInterface != null) {
            try {
                mInterface.close();
            } catch (IOException e) {
                e.printStackTrace();
            }
        }
        super.onDestroy();
    }
}
