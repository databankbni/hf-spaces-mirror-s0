<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->boolean('tfa_enabled')->default(false)->after('password');
            $table->text('tfa_secret')->nullable()->after('tfa_enabled');
            $table->text('tfa_recovery_codes')->nullable()->after('tfa_secret');
            $table->string('tfa_provider')->default('email')->after('tfa_recovery_codes');
        });
    }

    public function down(): void
    {
        Schema::table('users', function (Blueprint $table) {
            $table->dropColumn(['tfa_enabled', 'tfa_secret', 'tfa_recovery_codes', 'tfa_provider']);
        });
    }
};
