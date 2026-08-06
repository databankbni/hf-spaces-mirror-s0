package com.example.childmonitor;

import com.google.gson.annotations.SerializedName;

/** Request body for POST /api/register */
public class RegisterRequest {
    @SerializedName("deviceId")
    public String deviceId;

    @SerializedName("waNumber")
    public String waNumber;

    @SerializedName("fcmToken")
    public String fcmToken;

    public RegisterRequest(String deviceId, String waNumber, String fcmToken) {
        this.deviceId = deviceId;
        this.waNumber = waNumber;
        this.fcmToken = fcmToken;
    }
}
