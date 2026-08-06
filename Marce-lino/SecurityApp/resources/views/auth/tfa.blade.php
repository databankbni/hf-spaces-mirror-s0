@extends('layouts.app')

@section('title', 'Two-Factor Authentication')

@section('content')
<div class="max-w-md mx-auto">
    <div class="bg-white shadow-md rounded-lg p-6">
        <h2 class="text-2xl font-bold mb-6 text-center">Two-Factor Authentication</h2>

        <p class="text-gray-600 text-center mb-4">
            A verification code has been sent to {{ $email ?? 'your email' }}.
            Please enter it below to complete login.
        </p>

        <form method="POST" action="{{ route('tfa.verify') }}">
            @csrf

            <div class="mb-4">
                <label for="code" class="block text-sm font-medium text-gray-700 mb-1">Verification Code</label>
                <input id="code" type="text" name="code" required autofocus maxlength="6"
                    class="w-full px-3 py-2 text-center text-2xl tracking-widest border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="000000">
            </div>

            <button type="submit"
                class="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 transition">
                Verify
            </button>

            <div class="mt-4 text-center">
                <a href="{{ route('tfa.resend') }}" class="text-blue-600 hover:underline text-sm">Resend Code</a>
            </div>
        </form>
    </div>
</div>
@endsection
