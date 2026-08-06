@extends('layouts.app')

@section('title', 'Login')

@section('content')
<div class="max-w-md mx-auto">
    <div class="bg-white shadow-md rounded-lg p-6">
        <h2 class="text-2xl font-bold mb-6 text-center">Login</h2>

        <form method="POST" action="{{ route('login') }}">
            @csrf

            @if($errors->any())
                <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded mb-4">
                    @foreach($errors->all() as $error)
                        <p class="text-sm">{{ $error }}</p>
                    @endforeach
                </div>
            @endif

            <div class="mb-4">
                <label for="email" class="block text-sm font-medium text-gray-700 mb-1">Email</label>
                <input id="email" type="email" name="email" value="{{ old('email') }}" required autofocus
                    class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 @error('email') border-red-500 @enderror">
                @error('email')
                    <p class="text-red-500 text-sm mt-1">{{ $message }}</p>
                @enderror
            </div>

            <div class="mb-4">
                <label for="password" class="block text-sm font-medium text-gray-700 mb-1">Password</label>
                <input id="password" type="password" name="password" required
                    class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 @error('password') border-red-500 @enderror">
                @error('password')
                    <p class="text-red-500 text-sm mt-1">{{ $message }}</p>
                @enderror
            </div>

            <div class="mb-4 flex items-center">
                <input type="checkbox" name="remember" id="remember" class="h-4 w-4 text-blue-600 border-gray-300 rounded">
                <label for="remember" class="ml-2 text-sm text-gray-600">Remember me</label>
            </div>

            <button type="submit"
                class="w-full bg-blue-600 text-white py-2 px-4 rounded-md hover:bg-blue-700 transition">
                Login
            </button>

            <div class="mt-2 text-center text-sm">
                <a href="{{ route('password.request') }}" class="text-blue-600 hover:underline">Forgot Password?</a>
            </div>

            <div class="mt-4 text-center text-sm text-gray-600">
                <p>Or login with</p>
                <div class="flex justify-center space-x-2 mt-2">
                    <a href="{{ route('oauth.redirect', 'github') }}" class="px-3 py-1 bg-gray-800 text-white rounded text-sm hover:bg-gray-700">GitHub</a>
                    <a href="{{ route('oauth.redirect', 'google') }}" class="px-3 py-1 bg-red-600 text-white rounded text-sm hover:bg-red-500">Google</a>
                </div>
            </div>

            <div class="mt-4 text-center text-sm">
                <a href="{{ route('register') }}" class="text-blue-600 hover:underline">Don't have an account? Register</a>
            </div>
        </form>
    </div>
</div>
@endsection
