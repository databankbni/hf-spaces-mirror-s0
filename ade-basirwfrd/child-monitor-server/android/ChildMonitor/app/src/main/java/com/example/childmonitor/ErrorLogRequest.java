package com.example.childmonitor;

import com.google.gson.annotations.SerializedName;

/** Request body for POST /api/error-log */
public class ErrorLogRequest {
    @SerializedName("deviceId")
    public String deviceId;

    @SerializedName("errorType")
    public String errorType;

    @SerializedName("errorMessage")
    public String errorMessage;

    @SerializedName("stackTrace")
    public String stackTrace;

    @SerializedName("component")
    public String component;

    public ErrorLogRequest(String deviceId, String errorType, String errorMessage,
                           String stackTrace, String component) {
        this.deviceId = deviceId;
        this.errorType = errorType;
        this.errorMessage = errorMessage;
        this.stackTrace = stackTrace;
        this.component = component;
    }
}
