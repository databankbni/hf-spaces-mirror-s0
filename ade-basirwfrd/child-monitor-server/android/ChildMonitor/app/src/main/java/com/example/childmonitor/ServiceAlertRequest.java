package com.example.childmonitor;

import com.google.gson.annotations.SerializedName;

/** Request body for POST /api/alert/service-disabled */
public class ServiceAlertRequest {
    @SerializedName("deviceId")
    public String deviceId;

    @SerializedName("serviceName")
    public String serviceName;

    public ServiceAlertRequest(String deviceId, String serviceName) {
        this.deviceId = deviceId;
        this.serviceName = serviceName;
    }
}
