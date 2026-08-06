<?php

namespace App\Http\Controllers\Admin;

use App\Http\Controllers\Controller;
use App\Models\Backup;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Storage;

class BackupController extends Controller
{
    public function index()
    {
        $backups = Backup::orderByDesc('created_at')->get();

        $disk = Storage::build([
            'driver' => 'local',
            'root' => storage_path('app/backups'),
        ]);

        return view('backups.index', compact('backups', 'disk'));
    }

    public function create(): RedirectResponse
    {
        Artisan::call('security:backup', ['--type' => 'manual']);
        return redirect()->route('admin.backups.index')
            ->with('status', trim(Artisan::output()));
    }

    public function download(Backup $backup)
    {
        $disk = Storage::build([
            'driver' => 'local',
            'root' => storage_path('app/backups'),
        ]);

        if (!$disk->exists($backup->filename)) {
            return back()->withErrors(['error' => 'Backup file not found.']);
        }

        return response()->download(
            $disk->path($backup->filename),
            $backup->filename,
        );
    }

    public function destroy(Backup $backup): RedirectResponse
    {
        $disk = Storage::build([
            'driver' => 'local',
            'root' => storage_path('app/backups'),
        ]);

        if ($disk->exists($backup->filename)) {
            $disk->delete($backup->filename);
        }

        $backup->delete();

        return redirect()->route('admin.backups.index')
            ->with('status', 'Backup deleted successfully.');
    }
}
