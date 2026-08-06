<?php

namespace App\Http\Middleware;

use App\Models\ActivityLog;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class LogActivity
{
    public function handle(Request $request, Closure $next, string $action = null): Response
    {
        $response = $next($request);

        if ($user = $request->user()) {
            ActivityLog::create([
                'user_id' => $user->id,
                'action' => $action ?? $request->method() . ' ' . $request->path(),
                'description' => $request->method() . ' ' . $request->path(),
                'ip_address' => $request->ip(),
                'user_agent' => $request->userAgent(),
                'metadata' => [
                    'method' => $request->method(),
                    'path' => $request->path(),
                    'status' => $response->getStatusCode(),
                ],
            ]);
        }

        return $response;
    }
}
