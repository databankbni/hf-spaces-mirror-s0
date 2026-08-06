<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\ActivityLog;

class ActivityLogController extends Controller
{
    public function index()
    {
        $logs = ActivityLog::with('user')
            ->orderByDesc('created_at')
            ->paginate(50);

        return view('activity-logs.index', compact('logs'));
    }

    public function show(ActivityLog $log)
    {
        return view('activity-logs.show', compact('log'));
    }
}
