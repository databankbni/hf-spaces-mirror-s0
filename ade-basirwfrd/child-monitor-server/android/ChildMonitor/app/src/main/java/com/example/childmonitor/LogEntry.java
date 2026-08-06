package com.example.childmonitor;

import androidx.room.Entity;
import androidx.room.PrimaryKey;

@Entity
public class LogEntry {
    @PrimaryKey(autoGenerate = true)
    public int id;

    public String packageName;
    public String appName;
    public String url;
    public long timestamp;
    public boolean sent;
    public boolean isJudi;
}
