@extends('layouts.app')

@section('title', 'Dashboard')

@section('content')
<div class="max-w-4xl mx-auto">
    <h1 class="text-3xl font-bold mb-6">Dashboard</h1>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <div class="bg-white shadow rounded-lg p-6">
            <h3 class="text-gray-500 text-sm font-medium">Account</h3>
            <p class="text-xl font-bold">{{ $user->name }}</p>
            <p class="text-gray-500 text-sm">{{ $user->email }}</p>
        </div>
        <div class="bg-white shadow rounded-lg p-6">
            <h3 class="text-gray-500 text-sm font-medium">TFA Status</h3>
            <p class="text-xl font-bold {{ $user->tfa_enabled ? 'text-green-600' : 'text-red-600' }}">
                {{ $user->tfa_enabled ? 'Enabled' : 'Disabled' }}
            </p>
            <a href="{{ route('tfa.setup') }}" class="text-blue-600 text-sm hover:underline">Manage</a>
        </div>
        <div class="bg-white shadow rounded-lg p-6">
            <h3 class="text-gray-500 text-sm font-medium">OAuth</h3>
            <p class="text-xl font-bold">{{ $user->hasOAuth() ? ucfirst($user->oauth_provider) : 'None' }}</p>
        </div>
    </div>

    <div class="bg-white shadow rounded-lg p-6">
        <h2 class="text-xl font-bold mb-4">Recent Activity</h2>
        @if($recentLogs->isEmpty())
            <p class="text-gray-500">No recent activity.</p>
        @else
            <table class="w-full text-sm">
                <thead>
                    <tr class="border-b">
                        <th class="text-left py-2">Action</th>
                        <th class="text-left py-2">IP</th>
                        <th class="text-left py-2">Date</th>
                    </tr>
                </thead>
                <tbody>
                    @foreach($recentLogs as $log)
                        <tr class="border-b hover:bg-gray-50">
                            <td class="py-2">{{ $log->description }}</td>
                            <td class="py-2 text-gray-500">{{ $log->ip_address }}</td>
                            <td class="py-2 text-gray-500">{{ $log->created_at->diffForHumans() }}</td>
                        </tr>
                    @endforeach
                </tbody>
            </table>
        @endif
    </div>

    <div class="mt-6 bg-white shadow rounded-lg p-6">
        <h2 class="text-xl font-bold mb-4">Security Commands</h2>
        <div class="space-y-2 text-sm">
            <p><code class="bg-gray-100 px-2 py-1 rounded">php artisan security:generate-password</code> - Generate a strong password</p>
            <p><code class="bg-gray-100 px-2 py-1 rounded">php artisan security:generate-password --length=32 --count=5</code> - Generate 5 passwords of length 32</p>
            <p><code class="bg-gray-100 px-2 py-1 rounded">php artisan security:backup</code> - Backup the database</p>
            <p><code class="bg-gray-100 px-2 py-1 rounded">php artisan security:restore --latest</code> - Restore from latest backup</p>
        </div>
    </div>
</div>
@endsection
