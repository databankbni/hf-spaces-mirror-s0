package com.example.childmonitor;

import com.google.gson.annotations.SerializedName;

/** Response GET /api/config — URL kanonik server & rekomendasi interval. */
public class PublicConfigResponse {
    @SerializedName("publicBaseUrl")
    public String publicBaseUrl;

    @SerializedName("heartbeatRecommendedSec")
    public int heartbeatRecommendedSec;

    @SerializedName("version")
    public String version;
}
