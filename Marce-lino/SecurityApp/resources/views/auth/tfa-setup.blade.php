@extends('layouts.app')

@section('title', 'Two-Factor Authentication Setup')

@section('content')
<div class="max-w-2xl mx-auto">
    <div class="bg-white shadow-md rounded-lg p-6">
        <h2 class="text-2xl font-bold mb-6">Two-Factor Authentication</h2>

        @if(session('recovery_codes'))
            <div class="bg-yellow-50 border border-yellow-400 text-yellow-800 px-4 py-3 rounded mb-4">
                <h3 class="font-bold mb-2">Save Your Recovery Codes</h3>
                <p class="text-sm mb-3">Each code can only be used once. Store these in a secure location.</p>
                <div class="bg-white p-3 rounded font-mono text-sm">
                    @foreach(session('recovery_codes') as $code)
                        <div>{{ $code }}</div>
                    @endforeach
                </div>
            </div>
        @endif

        @if($user->tfa_enabled)
            <div class="bg-green-50 border border-green-400 text-green-700 px-4 py-3 rounded mb-4">
                Two-factor authentication is currently <strong>ENABLED</strong>.
            </div>

            @if($recoveryCodes)
                <div class="mb-4">
                    <h3 class="font-bold mb-2">Your Recovery Codes</h3>
                    <p class="text-sm text-gray-600 mb-2">Use these codes if you lose access to your email.</p>
                    <div class="bg-gray-50 p-3 rounded font-mono text-sm">
                        @foreach($recoveryCodes as $code)
                            <div>{{ $code }}</div>
                        @endforeach
                    </div>
                </div>
            @endif

            <form method="POST" action="{{ route('tfa.disable') }}">
                @csrf
                <div class="mb-4">
                    <label for="password" class="block text-sm font-medium text-gray-700 mb-1">Enter your password to disable TFA</label>
                    <input id="password" type="password" name="password" required
                        class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-red-500">
                </div>
                <button type="submit" class="bg-red-600 text-white px-4 py-2 rounded-md hover:bg-red-700 transition"
                    onclick="return confirm('Are you sure you want to disable TFA?')">
                    Disable Two-Factor Authentication
                </button>
            </form>
        @else
            <div class="bg-gray-50 border border-gray-300 text-gray-700 px-4 py-3 rounded mb-4">
                Two-factor authentication is currently <strong>DISABLED</strong>.
            </div>
            <p class="text-gray-600 mb-4">Enable two-factor authentication to add an extra layer of security to your account.</p>

            <form method="POST" action="{{ route('tfa.enable') }}">
                @csrf
                <button type="submit"
                    class="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition">
                    Enable Two-Factor Authentication
                </button>
            </form>
        @endif
    </div>
</div>
@endsection
