package com.example.childmonitor;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import retrofit2.Call;
import retrofit2.Callback;
import retrofit2.Response;

/**
 * Client-side gambling/blocked site filter.
 * Checks against BOTH hardcoded keywords AND a dynamic blocklist synced from the server.
 */
public class JudiFilter {

    private static final String TAG = "JudiFilter";

    // Dynamic blocklist synced from server
    private static final Set<String> serverBlocklist = new HashSet<>();
    private static long lastSyncTime = 0;
    private static final long SYNC_INTERVAL = 60 * 1000L; // Sync every 60 seconds

    private static final List<String> JUDI_KEYWORDS = Arrays.asList(
            "judi", "slot", "poker", "togel", "casino", "bet", "bola",
            "gambling", "taruhan", "bandar", "jackpot", "scatter", "gacor",
            "maxwin", "pragmatic", "pgsoft", "livecasino", "sportsbook",
            "roulette", "blackjack", "baccarat", "sicbo", "judol",
            "slotgacor", "cuan",
            "sbobet", "mansion88", "m88", "w88", "fun88", "we88", "md88",
            "bk8", "dafabet", "cmd368", "ibcbet", "maxbet", "188bet",
            "longfu88", "kawanslot", "naga303", "dewapoker", "idnpoker",
            "joker123", "mpo88", "parimatch", "paripesa", "1xbet", "1win",
            "mostbet", "melbet", "roobet", "bcgame"
    );

    /** Fallback lokal (anti-judol saja — bukan antibokep). Full list dari server /api/blocklist. */
    private static final List<String> JUDI_DOMAINS = Arrays.asList(
            "sbobet.com", "ibcbet.com", "maxbet.com", "188bet.com",
            "bet365.com", "1xbet.com", "22bet.com", "melbet.com",
            "m88.com", "w88.com", "fun88.com", "we88.com", "md88.com",
            "dafabet.com", "cmd368.com", "bk8.com", "bk8.plus", "longfu88.com",
            "poker88.com", "idnpoker.com", "dewapoker.com", "pokerstars.com",
            "togel.com", "togel4d.com", "totobet.com", "indotogel.com",
            "slot88.com", "joker123.com", "joker388.com", "slotgacor.com",
            "judionline.com", "judibola.com", "pragmaticplay.com", "pgsoft.com",
            "bonanza88.com", "mpo88.com", "ole777.com", "stake.com", "bc.game",
            "mostbet.com", "kawanslot.com", "naga303.com", "parimatch.com",
            "1win.com", "roobet.com", "bheestybaulk.top", "aungudie.com", "zlink.fun"
    );

    /**
     * Sync blocklist from server. Call this periodically.
     */
    public static void syncBlocklist(Context context) {
        long now = System.currentTimeMillis();
        if (now - lastSyncTime < SYNC_INTERVAL) return; // Don't sync too often
        lastSyncTime = now;

        try {
            RetrofitClient.getInstance(context).getBlocklist().enqueue(new Callback<BlocklistResponse>() {
                @Override
                public void onResponse(Call<BlocklistResponse> call, Response<BlocklistResponse> response) {
                    if (response.isSuccessful() && response.body() != null && response.body().domains != null) {
                        synchronized (serverBlocklist) {
                            serverBlocklist.clear();
                            for (String d : response.body().domains) {
                                serverBlocklist.add(d.toLowerCase());
                            }
                        }
                        Log.d(TAG, "Blocklist synced: " + serverBlocklist.size() + " domains from server");
                    }
                }

                @Override
                public void onFailure(Call<BlocklistResponse> call, Throwable t) {
                    Log.w(TAG, "Blocklist sync failed: " + t.getMessage());
                }
            });
        } catch (Exception e) {
            Log.w(TAG, "Blocklist sync error: " + e.getMessage());
        }
    }

    /**
     * Check if a URL is a gambling/blocked site
     */
    public static boolean isJudiSite(String url) {
        if (url == null || url.isEmpty()) return false;

        String urlLower = url.toLowerCase();
        String host = extractHost(urlLower);

        // 1. Check against hardcoded domain list
        if (host != null) {
            for (String domain : JUDI_DOMAINS) {
                if (host.equals(domain) || host.endsWith("." + domain)) {
                    Log.d(TAG, "BLOCKED (hardcoded domain): " + url);
                    return true;
                }
            }
        }

        // 2. Check against server-synced blocklist
        if (host != null) {
            synchronized (serverBlocklist) {
                for (String domain : serverBlocklist) {
                    if (host.equals(domain) || host.endsWith("." + domain)) {
                        Log.d(TAG, "BLOCKED (server blocklist): " + url);
                        return true;
                    }
                }
            }
        }

        // 3. Check keywords in hostname
        if (host != null) {
            for (String keyword : JUDI_KEYWORDS) {
                if (host.contains(keyword)) {
                    Log.d(TAG, "BLOCKED (keyword in host): " + url);
                    return true;
                }
            }
        }

        // 4. Check specific keywords in URL path
        String[] pathKeywords = {"slot", "togel", "casino", "poker", "sportsbook"};
        for (String keyword : pathKeywords) {
            if (urlLower.contains("/" + keyword)) {
                Log.d(TAG, "BLOCKED (keyword in path): " + url);
                return true;
            }
        }

        return false;
    }

    private static String extractHost(String url) {
        try {
            String host = url;
            if (host.contains("://")) {
                host = host.substring(host.indexOf("://") + 3);
            }
            if (host.contains("/")) {
                host = host.substring(0, host.indexOf("/"));
            }
            if (host.contains(":")) {
                host = host.substring(0, host.indexOf(":"));
            }
            return host;
        } catch (Exception e) {
            return null;
        }
    }
}
