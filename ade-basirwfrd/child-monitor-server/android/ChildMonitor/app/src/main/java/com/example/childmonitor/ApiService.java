package com.example.childmonitor;

import retrofit2.Call;
import retrofit2.http.Body;
import retrofit2.http.GET;
import retrofit2.http.POST;

public interface ApiService {

    @POST("api/register")
    Call<Void> register(@Body RegisterRequest request);

    @POST("api/log")
    Call<Void> sendLog(@Body LogData logData);

    @GET("api/blocklist")
    Call<BlocklistResponse> getBlocklist();

    /** Konfigurasi publik (URL kanonik server, interval heartbeat). */
    @GET("api/config")
    Call<PublicConfigResponse> getPublicConfig();

    @POST("api/heartbeat")
    Call<Void> heartbeat(@Body HeartbeatRequest request);

    @POST("api/alert/service-disabled")
    Call<Void> alertServiceDisabled(@Body ServiceAlertRequest request);

    @POST("api/alert/vpn-detected")
    Call<Void> alertVpnDetected(@Body HeartbeatRequest request);

    @POST("api/error-log")
    Call<Void> sendErrorLog(@Body ErrorLogRequest request);
}
