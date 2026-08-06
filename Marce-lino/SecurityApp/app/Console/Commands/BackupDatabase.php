<?php

namespace App\Console\Commands;

use App\Models\Backup;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Storage;

class BackupDatabase extends Command
{
    protected $signature = 'security:backup
        {--type=manual : Backup type (manual/automated/scheduled)}';

    protected $description = 'Backup the database';

    public function handle(): int
    {
        $this->info('Starting database backup...');

        $disk = Storage::build([
            'driver' => 'local',
            'root' => storage_path('app/backups'),
        ]);

        $filename = 'backup-' . now()->format('Y-m-d_H-i-s') . '.sqlite';
        $dbPath = database_path('database.sqlite');

        if (!file_exists($dbPath)) {
            $this->error('Database file not found.');
            return self::FAILURE;
        }

        try {
            $disk->put($filename, file_get_contents($dbPath));

            Backup::create([
                'filename' => $filename,
                'path' => 'backups/' . $filename,
                'size' => filesize($dbPath),
                'type' => $this->option('type'),
                'metadata' => [
                    'original_size' => filesize($dbPath),
                    'tables' => $this->getTableCount(),
                ],
            ]);

            $this->info("Backup created: {$filename}");

            return self::SUCCESS;
        } catch (\Exception $e) {
            $this->error("Backup failed: {$e->getMessage()}");
            return self::FAILURE;
        }
    }

    private function getTableCount(): int
    {
        try {
            return \DB::select('SELECT COUNT(*) as count FROM sqlite_master WHERE type="table"')[0]->count;
        } catch (\Exception) {
            return 0;
        }
    }
}
