<?php

namespace App\Http\Controllers\Auth;

use App\Helpers\SecurityHelper;
use App\Http\Controllers\Controller;
use App\Models\ActivityLog;
use Illuminate\Http\RedirectResponse;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Log;
use Laravel\Socialite\Facades\Socialite;

class OAuthController extends Controller
{
    public function redirect(string $provider): RedirectResponse
    {
        $this->validateProvider($provider);
        return Socialite::driver($provider)->redirect();
    }

    public function callback(string $provider): RedirectResponse
    {
        $this->validateProvider($provider);

        try {
            $socialUser = Socialite::driver($provider)->user();
        } catch (\Exception) {
            return redirect('/login')->withErrors(['email' => 'Authentication failed. Please try again.']);
        }

        $user = \App\Models\User::where('oauth_provider', $provider)
            ->where('oauth_id', $socialUser->getId())
            ->first();

        if (!$user) {
            $user = \App\Models\User::where('email', $socialUser->getEmail())->first();

            if (!$user) {
                return redirect('/login')->withErrors(['email' => 'No account found with this email. Please register first.']);
            }

            $user->update([
                'oauth_provider' => $provider,
                'oauth_id' => $socialUser->getId(),
            ]);
        }

        Auth::login($user);

        ActivityLog::create([
            'user_id' => $user->id,
            'action' => 'oauth_login',
            'description' => "Logged in via {$provider}",
            'ip_address' => request()->ip(),
            'user_agent' => request()->userAgent(),
            'metadata' => ['provider' => $provider],
        ]);

        if ($user->tfa_enabled) {
            $code = SecurityHelper::generateTfaCode();
            Cache::put('tfa_code_' . $user->id, $code, now()->addMinutes(10));
            try {
                $user->notify(new \App\Notifications\TfaCodeNotification($code));
            } catch (\Throwable $e) {
                Log::warning('Failed to send TFA code notification: ' . $e->getMessage());
            }
            Auth::logout();
            session(['tfa_user_id' => $user->id]);
            return redirect()->route('tfa.verify');
        }

        return redirect()->intended('/dashboard');
    }

    private function validateProvider(string $provider): void
    {
        if (!in_array($provider, ['github', 'google'])) {
            abort(404);
        }
    }
}
