package com.example.childmonitor;

import com.google.gson.annotations.SerializedName;

/** Request body for POST /api/log */
public class LogData {
    @SerializedName("deviceId")
    public String deviceId;

    @SerializedName("packageName")
    public String packageName;

    @SerializedName("appName")
    public String appName;

    @SerializedName("url")
    public String url;

    @SerializedName("timestamp")
    public long timestamp;

    @SerializedName("isJudi")
    public boolean isJudi;

    public LogData(String deviceId, String packageName, String appName, String url, long timestamp, boolean isJudi) {
        this.deviceId = deviceId;
        this.packageName = packageName;
        this.appName = appName;
        this.url = url;
        this.timestamp = timestamp;
        this.isJudi = isJudi;
    }
}
