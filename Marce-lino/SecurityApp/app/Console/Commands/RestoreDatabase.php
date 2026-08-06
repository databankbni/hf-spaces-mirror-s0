<?php

namespace App\Console\Commands;

use App\Models\Backup;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Storage;

class RestoreDatabase extends Command
{
    protected $signature = 'security:restore
        {--backup= : The backup filename to restore from}
        {--latest : Restore from the latest backup}';

    protected $description = 'Restore the database from a backup';

    public function handle(): int
    {
        $disk = Storage::build([
            'driver' => 'local',
            'root' => storage_path('app/backups'),
        ]);

        $backup = null;

        if ($this->option('latest')) {
            $backup = Backup::latest()->first();
        } elseif ($filename = $this->option('backup')) {
            $backup = Backup::where('filename', $filename)->first();
        }

        if (!$backup) {
            $available = Backup::orderByDesc('created_at')->get();

            if ($available->isEmpty()) {
                $this->error('No backups found.');
                return self::FAILURE;
            }

            $this->info('Available backups:');
            foreach ($available as $b) {
                $this->line("  [{$b->id}] {$b->filename} ({$b->created_at})");
            }

            $id = $this->ask('Enter backup ID to restore');
            $backup = Backup::find($id);

            if (!$backup) {
                $this->error('Invalid backup ID.');
                return self::FAILURE;
            }
        }

        if (!$this->confirm("Are you sure you want to restore from {$backup->filename}? This will overwrite your current database.")) {
            $this->info('Restore cancelled.');
            return self::SUCCESS;
        }

        $this->info("Restoring from: {$backup->filename}...");

        if (!$disk->exists($backup->filename)) {
            $this->error("Backup file not found: {$backup->filename}");
            return self::FAILURE;
        }

        try {
            $dbPath = database_path('database.sqlite');
            file_put_contents($dbPath, $disk->get($backup->filename));
            $this->info('Database restored successfully.');

            return self::SUCCESS;
        } catch (\Exception $e) {
            $this->error("Restore failed: {$e->getMessage()}");
            return self::FAILURE;
        }
    }
}
