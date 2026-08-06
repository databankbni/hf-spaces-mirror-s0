<?php

namespace App\Rules;

use Closure;
use Illuminate\Contracts\Validation\ValidationRule;

class StrongPassword implements ValidationRule
{
    public function __construct(
        private int $minLength = 8,
        private bool $requireUpper = true,
        private bool $requireLower = true,
        private bool $requireNumber = true,
        private bool $requireSymbol = true,
    ) {}

    public function validate(string $attribute, mixed $value, Closure $fail): void
    {
        $value = (string) $value;

        if (strlen($value) < $this->minLength) {
            $fail("The {$attribute} must be at least {$this->minLength} characters.");
        }

        if ($this->requireUpper && !preg_match('/[A-Z]/', $value)) {
            $fail("The {$attribute} must contain at least one uppercase letter.");
        }

        if ($this->requireLower && !preg_match('/[a-z]/', $value)) {
            $fail("The {$attribute} must contain at least one lowercase letter.");
        }

        if ($this->requireNumber && !preg_match('/[0-9]/', $value)) {
            $fail("The {$attribute} must contain at least one number.");
        }

        if ($this->requireSymbol && !preg_match('/[^A-Za-z0-9]/', $value)) {
            $fail("The {$attribute} must contain at least one symbol.");
        }
    }
}
