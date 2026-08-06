package com.example.childmonitor;

import com.google.gson.annotations.SerializedName;

import java.util.List;

/** Response body for GET /api/blocklist */
public class BlocklistResponse {
    @SerializedName("domains")
    public List<String> domains;

    @SerializedName("keywords")
    public List<String> keywords;

    @SerializedName("version")
    public int version;
}
