@extends('layouts.app')

@section('title', 'Backups')

@section('content')
<div class="max-w-6xl mx-auto">
    <div class="flex justify-between items-center mb-6">
        <h1 class="text-3xl font-bold">Database Backups</h1>
        <form method="POST" action="{{ route('admin.backups.create') }}">
            @csrf
            <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition">
                Create Backup
            </button>
        </form>
    </div>

    <div class="bg-white shadow rounded-lg overflow-hidden">
        <table class="w-full text-sm">
            <thead class="bg-gray-50">
                <tr>
                    <th class="text-left px-4 py-3">Filename</th>
                    <th class="text-left px-4 py-3">Type</th>
                    <th class="text-left px-4 py-3">Size</th>
                    <th class="text-left px-4 py-3">Date</th>
                    <th class="text-right px-4 py-3">Actions</th>
                </tr>
            </thead>
            <tbody>
                @forelse($backups as $backup)
                    <tr class="border-t hover:bg-gray-50">
                        <td class="px-4 py-3 font-mono text-sm">{{ $backup->filename }}</td>
                        <td class="px-4 py-3">
                            <span class="px-2 py-1 rounded text-xs {{ $backup->type === 'manual' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800' }}">
                                {{ $backup->type }}
                            </span>
                        </td>
                        <td class="px-4 py-3 text-gray-500">
                            @if($backup->size > 1048576)
                                {{ number_format($backup->size / 1048576, 2) }} MB
                            @else
                                {{ number_format($backup->size / 1024, 2) }} KB
                            @endif
                        </td>
                        <td class="px-4 py-3 text-gray-500">{{ $backup->created_at->format('Y-m-d H:i') }}</td>
                        <td class="px-4 py-3 text-right space-x-2">
                            <a href="{{ route('admin.backups.download', $backup) }}"
                                class="text-blue-600 hover:underline text-sm">Download</a>
                            <form method="POST" action="{{ route('admin.backups.destroy', $backup) }}" class="inline"
                                onsubmit="return confirm('Delete this backup?')">
                                @csrf @method('DELETE')
                                <button type="submit" class="text-red-600 hover:underline text-sm">Delete</button>
                            </form>
                        </td>
                    </tr>
                @empty
                    <tr class="border-t">
                        <td colspan="5" class="px-4 py-8 text-center text-gray-500">No backups found.</td>
                    </tr>
                @endforelse
            </tbody>
        </table>
    </div>
</div>
@endsection
