@extends('layouts.app')

@section('title', 'Activity Log Detail')

@section('content')
<div class="max-w-2xl mx-auto">
    <h1 class="text-3xl font-bold mb-6">Activity Log Detail</h1>

    <div class="bg-white shadow rounded-lg p-6">
        <dl class="space-y-4">
            <div>
                <dt class="text-sm text-gray-500">User</dt>
                <dd class="font-medium">{{ $log->user?->name ?? 'Guest' }} ({{ $log->user?->email ?? 'N/A' }})</dd>
            </div>
            <div>
                <dt class="text-sm text-gray-500">Action</dt>
                <dd><span class="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs">{{ $log->action }}</span></dd>
            </div>
            <div>
                <dt class="text-sm text-gray-500">Description</dt>
                <dd>{{ $log->description }}</dd>
            </div>
            <div>
                <dt class="text-sm text-gray-500">IP Address</dt>
                <dd>{{ $log->ip_address }}</dd>
            </div>
            <div>
                <dt class="text-sm text-gray-500">User Agent</dt>
                <dd class="text-sm text-gray-600 break-all">{{ $log->user_agent }}</dd>
            </div>
            <div>
                <dt class="text-sm text-gray-500">Date</dt>
                <dd>{{ $log->created_at->format('Y-m-d H:i:s') }}</dd>
            </div>
            @if($log->metadata)
                <div>
                    <dt class="text-sm text-gray-500">Metadata</dt>
                    <dd><pre class="bg-gray-50 p-2 rounded text-xs">{{ json_encode($log->metadata, JSON_PRETTY_PRINT) }}</pre></dd>
                </div>
            @endif
        </dl>
    </div>
</div>
@endsection
