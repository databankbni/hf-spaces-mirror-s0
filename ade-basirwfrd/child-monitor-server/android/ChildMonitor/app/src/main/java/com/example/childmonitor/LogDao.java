package com.example.childmonitor;

import androidx.room.Dao;
import androidx.room.Insert;
import androidx.room.Query;
import androidx.room.Update;

import java.util.List;

@Dao
public interface LogDao {
    @Insert
    void insert(LogEntry entry);

    @Query("SELECT * FROM LogEntry WHERE sent = 0 ORDER BY timestamp ASC")
    List<LogEntry> getUnsentLogs();

    @Update
    void update(LogEntry entry);

    @Query("DELETE FROM LogEntry WHERE sent = 1 AND timestamp < :beforeTimestamp")
    void deleteOldSentLogs(long beforeTimestamp);
}
