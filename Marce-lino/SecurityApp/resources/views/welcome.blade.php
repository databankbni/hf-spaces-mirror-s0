<!DOCTYPE html>
<html lang="{{ str_replace('_', '-', app()->getLocale()) }}">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ config('app.name', 'SecurityApp') }}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
            body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background: #f8fafc; margin: 0; padding: 0; color: #1e293b; }
            .container { max-width: 800px; margin: 0 auto; padding: 2rem; }
            header { text-align: center; padding: 3rem 0; }
            h1 { font-size: 2.5rem; margin: 0; color: #0f172a; }
            .subtitle { color: #64748b; font-size: 1.1rem; margin-top: 0.5rem; }
            .features { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin: 2rem 0; }
            .feature { background: white; padding: 1.5rem; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #e2e8f0; text-align: center; }
            .feature h3 { margin: 0 0 0.5rem; color: #0f172a; }
            .feature p { margin: 0; color: #64748b; font-size: 0.9rem; }
            .feature .icon { font-size: 2rem; margin-bottom: 0.5rem; }
            .actions { text-align: center; margin: 2rem 0; }
            .actions a, .actions button { display: inline-block; padding: 0.75rem 2rem; border-radius: 8px; font-weight: 600; text-decoration: none; margin: 0 0.5rem; cursor: pointer; border: none; }
            .btn-primary { background: #2563eb; color: white; }
            .btn-primary:hover { background: #1d4ed8; }
            .btn-outline { background: transparent; color: #2563eb; border: 2px solid #2563eb; }
            .btn-outline:hover { background: #eff6ff; }
            .security-badge { display: inline-block; background: #ecfdf5; color: #059669; padding: 0.25rem 0.75rem; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
        </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{{ config('app.name', 'SecurityApp') }}</h1>
            <p class="subtitle">Enterprise-grade security built into your Laravel application.</p>
        </header>

        <div style="text-align: center; margin-bottom: 2rem;">
            <span class="security-badge">&#10003; 8 Security Features Active</span>
        </div>

        <div class="features">
            <div class="feature">
                <div class="icon">&#128274;</div>
                <h3>Strong Passwords</h3>
                <p>Auto-generated passwords with uppercase, lowercase, symbols & max length enforcement.</p>
            </div>
            <div class="feature">
                <div class="icon">&#128476;</div>
                <h3>Encryption & Hashing</h3>
                <p>AES-256 encryption + bcrypt hashing with configurable cost factors.</p>
            </div>
            <div class="feature">
                <div class="icon">&#128179;</div>
                <h3>TFA / MFA</h3>
                <p>Email-based two-factor authentication with recovery codes.</p>
            </div>
            <div class="feature">
                <div class="icon">&#128203;</div>
                <h3>Activity Logs</h3>
                <p>Comprehensive audit trail of all user actions with IP & user agent tracking.</p>
            </div>
            <div class="feature">
                <div class="icon">&#128683;</div>
                <h3>Max Login Attempts</h3>
                <p>Rate-limited login (5 attempts max) with automatic throttling.</p>
            </div>
            <div class="feature">
                <div class="icon">&#128190;</div>
                <h3>Backup & Restore</h3>
                <p>Manual & automated database backups with one-click restore.</p>
            </div>
            <div class="feature">
                <div class="icon">&#128231;</div>
                <h3>Email Notifications</h3>
                <p>Login alerts, TFA codes, backup reports sent to your inbox.</p>
            </div>
            <div class="feature">
                <div class="icon">&#128279;</div>
                <h3>OAuth</h3>
                <p>Social login via GitHub, Google, Facebook, Twitter & LinkedIn.</p>
            </div>
        </div>

        <div class="actions">
            @auth
                <a href="{{ route('dashboard') }}" class="btn-primary">Go to Dashboard</a>
            @else
                <a href="{{ route('login') }}" class="btn-primary">Log in</a>
                <a href="{{ route('register') }}" class="btn-outline">Register</a>
            @endauth
        </div>

        <div style="text-align: center; margin-top: 2rem; padding: 1.5rem; background: #f1f5f9; border-radius: 12px;">
            <h3 style="margin: 0 0 0.75rem;">Security Commands</h3>
            <code style="display: block; margin: 0.25rem 0; font-size: 0.85rem;">php artisan security:generate-password --length=20 --count=5</code>
            <code style="display: block; margin: 0.25rem 0; font-size: 0.85rem;">php artisan security:backup</code>
            <code style="display: block; margin: 0.25rem 0; font-size: 0.85rem;">php artisan security:restore --latest</code>
        </div>

        <footer style="text-align: center; margin-top: 3rem; color: #94a3b8; font-size: 0.85rem;">
            <p>&copy; {{ date('Y') }} {{ config('app.name') }}. All rights reserved.</p>
        </footer>
    </div>
</body>
</html>
