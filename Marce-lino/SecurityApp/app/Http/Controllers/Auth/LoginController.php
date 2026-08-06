<?php

namespace App\Http\Controllers\Auth;

use App\Helpers\SecurityHelper;
use App\Http\Controllers\Controller;
use App\Models\ActivityLog;
use App\Notifications\LoginAlertNotification;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\RateLimiter as RateLimiterFacade;
use Illuminate\Validation\ValidationException;

class LoginController extends Controller
{
    public function showLoginForm()
    {
        return view('auth.login');
    }

    public function login(Request $request): RedirectResponse
    {
        $request->validate([
            'email' => 'required|email',
            'password' => 'required|string',
        ]);

        $this->checkTooManyAttempts($request);

        if (Auth::attempt($request->only('email', 'password'), $request->boolean('remember'))) {
            $request->session()->regenerate();

            RateLimiterFacade::clear($this->throttleKey($request));

            $user = Auth::user();

            if ($user->tfa_enabled) {
                $this->sendTfaCode($user);
                session(['tfa_pending' => true]);
                Auth::logout();
                session(['tfa_user_id' => $user->id]);
                return redirect()->route('tfa.verify');
            }

            $this->logActivity($user, $request, 'login', 'Successful login');
            $this->sendLoginAlert($user, $request, true);

            return redirect()->intended('/dashboard');
        }

        RateLimiterFacade::hit($this->throttleKey($request), 60);

        $this->logFailedAttempt($request);
        $this->sendFailedLoginAlert($request);

        throw ValidationException::withMessages([
            'email' => [trans('auth.failed')],
        ]);
    }

    public function logout(Request $request): RedirectResponse
    {
        $user = Auth::user();
        if ($user) {
            $this->logActivity($user, $request, 'logout', 'User logged out');
        }

        Auth::logout();
        $request->session()->invalidate();
        $request->session()->regenerateToken();

        return redirect('/');
    }

    private function checkTooManyAttempts(Request $request): void
    {
        if (!RateLimiterFacade::tooManyAttempts($this->throttleKey($request), 5)) {
            return;
        }

        $seconds = RateLimiterFacade::availableIn($this->throttleKey($request));

        throw ValidationException::withMessages([
            'email' => trans('auth.throttle', [
                'seconds' => $seconds,
                'minutes' => ceil($seconds / 60),
            ]),
        ]);
    }

    private function throttleKey(Request $request): string
    {
        return 'login:' . strtolower($request->input('email', '')) . '|' . $request->ip();
    }

    private function sendTfaCode($user): void
    {
        $code = SecurityHelper::generateTfaCode();
        Cache::put('tfa_code_' . $user->id, $code, now()->addMinutes(10));
        try {
            $user->notify(new \App\Notifications\TfaCodeNotification($code));
        } catch (\Throwable $e) {
            Log::warning('Failed to send TFA code notification: ' . $e->getMessage());
        }
    }

    private function logActivity($user, Request $request, string $action, string $description): void
    {
        ActivityLog::create([
            'user_id' => $user->id,
            'action' => $action,
            'description' => $description,
            'ip_address' => $request->ip(),
            'user_agent' => $request->userAgent(),
            'metadata' => ['email' => $user->email],
        ]);
    }

    private function sendLoginAlert($user, Request $request, bool $success): void
    {
        try {
            $user->notify(new LoginAlertNotification(
                $request->ip(),
                $request->userAgent(),
                $success,
            ));
        } catch (\Throwable $e) {
            Log::warning('Failed to send login alert notification: ' . $e->getMessage());
        }
    }

    private function logFailedAttempt(Request $request): void
    {
        $email = $request->input('email');
        $key = 'failed_logins:' . date('Y-m-d-H');

        $attempts = Cache::get($key, []);
        $attempts[] = [
            'email' => $email,
            'ip' => $request->ip(),
            'time' => now()->toDateTimeString(),
            'user_agent' => $request->userAgent(),
        ];
        Cache::put($key, $attempts, now()->addHours(1));
    }

    private function sendFailedLoginAlert(Request $request): void
    {
        $user = \App\Models\User::where('email', $request->input('email'))->first();
        if ($user) {
            $this->sendLoginAlert($user, $request, false);
        }
    }
}
