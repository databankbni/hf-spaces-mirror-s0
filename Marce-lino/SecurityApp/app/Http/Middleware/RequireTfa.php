<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class RequireTfa
{
    public function handle(Request $request, Closure $next): Response
    {
        $user = $request->user();

        if ($user && $user->tfa_enabled) {
            $verified = session('tfa_verified');
            $verifiedAt = session('tfa_verified_at');

            if (!$verified || !$verifiedAt || now()->timestamp - $verifiedAt > 3600) {
                session()->forget(['tfa_verified', 'tfa_verified_at']);
                return redirect()->route('tfa.verify');
            }
        }

        return $next($request);
    }
}
