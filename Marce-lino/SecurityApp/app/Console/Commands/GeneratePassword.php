<?php

namespace App\Console\Commands;

use App\Helpers\SecurityHelper;
use Illuminate\Console\Command;

class GeneratePassword extends Command
{
    protected $signature = 'security:generate-password
        {--length=16 : Password length}
        {--no-upper : Exclude uppercase letters}
        {--no-lower : Exclude lowercase letters}
        {--no-numbers : Exclude numbers}
        {--no-symbols : Exclude symbols}
        {--count=1 : Number of passwords to generate}';

    protected $description = 'Generate a strong random password';

    public function handle(): int
    {
        $count = (int) $this->option('count');
        $length = (int) $this->option('length');

        for ($i = 0; $i < $count; $i++) {
            $password = SecurityHelper::generatePassword(
                length: $length,
                upper: !$this->option('no-upper'),
                lower: !$this->option('no-lower'),
                numbers: !$this->option('no-numbers'),
                symbols: !$this->option('no-symbols'),
            );
            $this->line($password);
        }

        return self::SUCCESS;
    }
}
