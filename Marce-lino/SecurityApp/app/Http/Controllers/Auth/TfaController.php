<?php

namespace App\Http\Controllers\Auth;

use App\Helpers\SecurityHelper;
use App\Http\Controllers\Controller;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Log;

class TfaController extends Controller
{
    public function showVerifyForm()
    {
        $userId = session('tfa_user_id');
        if (!$userId) {
            return redirect('/login');
        }

        return view('auth.tfa', [
            'email' => \App\Models\User::find($userId)?->email,
        ]);
    }

    public function verify(Request $request): RedirectResponse
    {
        $request->validate(['code' => 'required|string|size:6']);

        $userId = session('tfa_user_id');
        if (!$userId) {
            return redirect('/login');
        }

        $cachedCode = Cache::get('tfa_code_' . $userId);

        if (!$cachedCode || $request->code !== $cachedCode) {
            return back()->withErrors(['code' => 'Invalid or expired verification code.']);
        }

        Cache::forget('tfa_code_' . $userId);
        Auth::loginUsingId($userId);

        session()->forget('tfa_user_id');
        session(['tfa_verified' => true, 'tfa_verified_at' => now()->timestamp]);

        $user = Auth::user();
        $user->notify(new \App\Notifications\LoginAlertNotification(
            $request->ip(),
            $request->userAgent(),
            true,
        ));

        return redirect()->intended('/dashboard');
    }

    public function resend(Request $request): RedirectResponse
    {
        $userId = session('tfa_user_id');
        if (!$userId) {
            return redirect('/login');
        }

        $user = \App\Models\User::find($userId);
        if (!$user) {
            return redirect('/login');
        }

        $code = SecurityHelper::generateTfaCode();
        Cache::put('tfa_code_' . $userId, $code, now()->addMinutes(10));
        try {
            $user->notify(new \App\Notifications\TfaCodeNotification($code));
        } catch (\Throwable $e) {
            Log::warning('Failed to resend TFA code notification: ' . $e->getMessage());
        }

        return back()->with('status', 'A new verification code has been sent.');
    }

    public function showSetupForm()
    {
        $user = Auth::user();
        $recoveryCodes = $user->tfa_recovery_codes
            ? json_decode($user->tfa_recovery_codes, true)
            : null;

        return view('auth.tfa-setup', [
            'user' => $user,
            'recoveryCodes' => $recoveryCodes,
        ]);
    }

    public function enable(Request $request): RedirectResponse
    {
        $user = Auth::user();

        $recoveryCodes = SecurityHelper::generateRecoveryCodes();

        $user->update([
            'tfa_enabled' => true,
            'tfa_secret' => SecurityHelper::encryptData($recoveryCodes),
            'tfa_recovery_codes' => json_encode($recoveryCodes),
            'tfa_provider' => 'email',
        ]);

        return redirect()->route('tfa.setup')->with('recovery_codes', $recoveryCodes);
    }

    public function disable(Request $request): RedirectResponse
    {
        $request->validate(['password' => 'required|current_password']);

        $user = Auth::user();
        $user->update([
            'tfa_enabled' => false,
            'tfa_secret' => null,
            'tfa_recovery_codes' => null,
        ]);

        return redirect()->route('tfa.setup')->with('status', 'Two-factor authentication disabled.');
    }
}
