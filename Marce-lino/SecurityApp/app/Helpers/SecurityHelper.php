<?php

namespace App\Helpers;

use Illuminate\Support\Facades\Crypt;

class SecurityHelper
{
    public static function generatePassword(int $length = 16, bool $upper = true, bool $lower = true, bool $numbers = true, bool $symbols = true): string
    {
        $chars = '';
        if ($upper) $chars .= 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
        if ($lower) $chars .= 'abcdefghijklmnopqrstuvwxyz';
        if ($numbers) $chars .= '0123456789';
        if ($symbols) $chars .= '!@#$%^&*()_+-=[]{}|;:,.<>?';

        if (empty($chars)) {
            $chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
        }

        $password = '';
        $max = strlen($chars) - 1;

        for ($i = 0; $i < $length; $i++) {
            $password .= $chars[random_int(0, $max)];
        }

        return $password;
    }

    public static function encryptData(mixed $data): string
    {
        return Crypt::encryptString(json_encode($data));
    }

    public static function decryptData(string $encrypted): mixed
    {
        return json_decode(Crypt::decryptString($encrypted), true);
    }

    public static function generateTfaCode(): string
    {
        return str_pad((string) random_int(100000, 999999), 6, '0', STR_PAD_LEFT);
    }

    public static function generateRecoveryCodes(int $count = 8): array
    {
        $codes = [];
        for ($i = 0; $i < $count; $i++) {
            $codes[] = strtoupper(
                implode('-', [
                    substr(bin2hex(random_bytes(3)), 0, 4),
                    substr(bin2hex(random_bytes(3)), 0, 4),
                    substr(bin2hex(random_bytes(3)), 0, 4),
                ])
            );
        }
        return $codes;
    }

    public static function maskEmail(string $email): string
    {
        $parts = explode('@', $email);
        $name = $parts[0];
        $domain = $parts[1] ?? '';
        $maskedName = substr($name, 0, 2) . str_repeat('*', max(0, strlen($name) - 2));
        return $maskedName . '@' . $domain;
    }
}
