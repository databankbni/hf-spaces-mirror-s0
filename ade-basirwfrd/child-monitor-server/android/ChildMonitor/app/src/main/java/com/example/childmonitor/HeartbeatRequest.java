package com.example.childmonitor;

import com.google.gson.annotations.SerializedName;

/** Request body for POST /api/heartbeat (dan alert VPN yang memakai deviceId). */
public class HeartbeatRequest {
    @SerializedName("deviceId")
    public String deviceId;

    @SerializedName("isDeviceOwner")
    public Boolean isDeviceOwner;

    @SerializedName("adminActive")
    public Boolean adminActive;

    @SerializedName("serviceRunning")
    public Boolean serviceRunning;

    @SerializedName("appVersion")
    public String appVersion;

    public HeartbeatRequest(String deviceId) {
        this.deviceId = deviceId;
    }

    public HeartbeatRequest(
            String deviceId,
            boolean isDeviceOwner,
            boolean adminActive,
            boolean serviceRunning,
            String appVersion) {
        this.deviceId = deviceId;
        this.isDeviceOwner = isDeviceOwner;
        this.adminActive = adminActive;
        this.serviceRunning = serviceRunning;
        this.appVersion = appVersion;
    }

    /** Heartbeat lengkap dari Context (MainService / Worker). */
    public static HeartbeatRequest fromContext(android.content.Context context, String deviceId) {
        String ver = BuildConfig.VERSION_NAME;
        try {
            ver = context.getPackageManager()
                    .getPackageInfo(context.getPackageName(), 0).versionName;
        } catch (Exception ignored) {
        }
        return new HeartbeatRequest(
                deviceId,
                DeviceOwnerController.isDeviceOwner(context),
                DeviceOwnerController.isAdminActive(context),
                true,
                ver != null ? ver : BuildConfig.VERSION_NAME
        );
    }
}
